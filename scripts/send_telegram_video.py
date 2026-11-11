#!/usr/bin/env python3
"""Reliable Telegram video delivery with adaptive MP4 compression and retries."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

MAX_UPLOAD_BYTES = 48_000_000
AUDIO_BITRATE = 96_000


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, timeout=45, check=True,
    )
    duration = float(result.stdout.strip())
    if duration <= 0:
        raise RuntimeError("ffprobe returned an invalid video duration.")
    return duration


def prepare_for_telegram(source: Path, temp_dir: Path) -> Path:
    size = source.stat().st_size
    if size <= MAX_UPLOAD_BYTES:
        print(f"Video is {size:,} bytes; no compression needed.", flush=True)
        return source

    duration = probe_duration(source)
    target = temp_dir / "telegram-ready.mp4"
    # Use successively lower target bitrates if the first encode is still
    # above the Bot API upload ceiling. Keep the source untouched.
    for attempt, factor in enumerate((1.0, 0.82, 0.68, 0.55), 1):
        total_bitrate = int((MAX_UPLOAD_BYTES * 8 / duration) * factor)
        video_bitrate = max(180_000, total_bitrate - AUDIO_BITRATE)
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", str(video_bitrate), "-maxrate", str(video_bitrate),
            "-bufsize", str(video_bitrate * 2),
            "-c:a", "aac", "-b:a", str(AUDIO_BITRATE),
            "-movflags", "+faststart", str(target),
        ]
        print(
            f"Compressing for Telegram (attempt {attempt}/4, "
            f"video bitrate {video_bitrate:,} bps)...",
            flush=True,
        )
        subprocess.run(command, check=True, timeout=1800)
        encoded_size = target.stat().st_size if target.is_file() else 0
        if 0 < encoded_size <= MAX_UPLOAD_BYTES:
            print(f"Telegram-ready video: {encoded_size:,} bytes.", flush=True)
            return target
        print(
            f"Compressed file is {encoded_size:,} bytes; reducing bitrate and retrying.",
            flush=True,
        )

    raise RuntimeError(
        f"Could not compress video below {MAX_UPLOAD_BYTES:,} bytes for Telegram. "
        "The original video and GitHub artifact are preserved."
    )


def send_video(path: Path, caption: str, token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    last_error = None
    for attempt in range(1, 5):
        try:
            with path.open("rb") as video_file:
                response = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption[:1024]},
                    files={"video": (path.name, video_file, "video/mp4")},
                    timeout=(30, 900),
                )
            if response.status_code == 429:
                try:
                    retry_after = int(
                        response.json().get("parameters", {}).get("retry_after", 15)
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    retry_after = 15
                if attempt < 4:
                    delay = min(max(retry_after, 2), 120)
                    print(f"Telegram rate-limited the upload; retrying in {delay}s.", flush=True)
                    time.sleep(delay)
                    continue
            if response.status_code in (500, 502, 503, 504):
                raise RuntimeError(
                    f"Telegram HTTP {response.status_code}: {response.text[:800]}"
                )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError(
                    "Telegram rejected the video: "
                    + str(payload.get("description", "unknown API error"))
                )
            message_id = (payload.get("result") or {}).get("message_id", "unknown")
            print(f"Telegram accepted the video (message_id={message_id}).", flush=True)
            return
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            last_error = exc
            if attempt < 4:
                delay = min(5 * attempt, 20)
                print(
                    f"Telegram upload attempt {attempt}/4 failed: {type(exc).__name__}: {exc}. "
                    f"Retrying in {delay}s.",
                    file=sys.stderr, flush=True,
                )
                time.sleep(delay)
    raise RuntimeError(f"Telegram upload failed after four attempts: {last_error}") from last_error


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/send_telegram_video.py VIDEO_PATH")
    source = Path(sys.argv[1]).expanduser().resolve()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    caption = os.getenv("TELEGRAM_CAPTION", "").strip()
    if not source.is_file() or source.stat().st_size <= 0:
        raise SystemExit(f"Video does not exist or is empty: {source}")
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured.")
    with tempfile.TemporaryDirectory(prefix="telegram-video-") as directory:
        prepared = prepare_for_telegram(source, Path(directory))
        send_video(prepared, caption, token, chat_id)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Telegram-triggered OCR meme editor. Never modifies or commits the source upload."""
import hashlib, math, os, re, subprocess, sys, tempfile, wave
from pathlib import Path

import cv2
import numpy as np
import pytesseract
import requests
from PIL import Image, ImageDraw, ImageFont

API = "https://api.telegram.org"
MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_UPLOAD = 48 * 1024 * 1024
RULES = [
    ("savage", re.compile(r"\b(destroyed|cooked|roasted|skill issue|obviously|genius|you asked|bro really)\b", re.I), "BRO GOT COOKED"),
    ("bruh", re.compile(r"\b(bruh|what even|nonsense|are you serious|wrong question)\b", re.I), "BRUH MOMENT"),
    ("shock", re.compile(r"\b(plot twist|unexpected|no way|wait what|did not expect)\b", re.I), "WAIT… WHAT?"),
    ("laugh", re.compile(r"\b(lol|lmao|haha|hilarious|funny|comedy)\b", re.I), "THAT'S ACTUALLY FUNNY"),
]

def tg(token, method, **kwargs):
    r = requests.post(f"{API}/bot{token}/{method}", timeout=90, **kwargs)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data["result"]

def say(token, chat, text):
    tg(token, "sendMessage", data={"chat_id": chat, "text": text})

def download(token, file_id, dest):
    info = tg(token, "getFile", json={"file_id": file_id})
    size = int(info.get("file_size") or 0)
    if size > MAX_DOWNLOAD:
        raise RuntimeError(f"Source is {size/1048576:.1f} MB; standard Telegram Bot API downloads are limited to 20 MB. Original remains untouched in this chat.")
    path = info.get("file_path")
    if not path:
        raise RuntimeError("Telegram did not return a file path.")
    total = 0
    with requests.get(f"{API}/file/bot{token}/{path}", stream=True, timeout=(30, 180)) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise RuntimeError("Download exceeded Telegram's 20 MB Bot API limit.")
                    f.write(chunk)
    if not total:
        raise RuntimeError("Telegram returned an empty file.")
    return total

def probe(path):
    import json
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-show_entries", "stream=codec_type", "-of", "json", str(path)],
                       check=True, capture_output=True, text=True)
    d = json.loads(p.stdout)
    duration = float(d.get("format", {}).get("duration", 0))
    audio = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    if duration <= 0:
        raise RuntimeError("Could not read video duration.")
    return duration, audio

def scan(path, duration):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("Could not open source video.")
    events, previous, last = [], "", -9.0
    t = 0.0
    while t < duration and len(events) < 8:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            h, w = frame.shape[:2]
            if w > 1000:
                frame = cv2.resize(frame, (1000, int(h * 1000 / w)))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 145, 255, cv2.THRESH_BINARY)[1]
            text = re.sub(r"\s+", " ", pytesseract.image_to_string(gray, config="--psm 6")).strip()
            digest = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
            if text and digest != previous and t - last >= 8:
                for category, pattern, label in RULES:
                    if pattern.search(text):
                        events.append({"time": t, "category": category, "label": label, "quote": text[-90:]})
                        last = t
                        break
            previous = digest
        t += 1.5
    cap.release()
    return events

def get_font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def sticker(event, path):
    im = Image.new("RGBA", (900, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, 894, 214), radius=32, fill=(12, 12, 18, 235),
                        outline=(255, 255, 255, 240), width=5)
    d.text((34, 24), event["label"], font=get_font(46), fill=(255, 225, 70, 255),
           stroke_width=2, stroke_fill=(0, 0, 0, 255))
    d.text((36, 108), event.get("quote", "")[-90:], font=get_font(22), fill="white")
    im.save(path)

def sound(category, path):
    rate, duration = 44100, 0.7 if category in ("savage", "shock") else 0.45
    t = np.arange(int(rate * duration), dtype=np.float32) / rate
    if category == "savage":
        f = 110 - 65 * t / duration
        phase = 2 * np.pi * np.cumsum(f) / rate
        x = np.sin(phase) * np.exp(-4*t)
        x += 0.18 * np.random.default_rng(7).normal(size=len(t)) * np.exp(-18*t)
    elif category == "bruh":
        x = np.sign(np.sin(2*np.pi*(120-30*t)*t)) * np.exp(-5*t)
    elif category == "shock":
        x = np.sin(2*np.pi*(800-500*t)*t) * np.exp(-4*t)
    else:
        x = (np.sin(2*np.pi*880*t) + .5*np.sin(2*np.pi*1320*t)) * np.exp(-6*t)
    x = (x / max(float(np.max(np.abs(x))), 1e-6) * .7 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(x.tobytes())

def render(source, output, events, duration, has_audio, work):
    stickers, sounds = [], []
    for i, event in enumerate(events):
        sp, ap = work / f"card{i}.png", work / f"sfx{i}.wav"
        sticker(event, sp); sound(event["category"], ap)
        stickers.append(sp); sounds.append(ap)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    silent = None
    if not has_audio:
        silent = 1
        cmd += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    image_start = 2 if not has_audio else 1
    for p in stickers:
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{duration:.3f}", "-i", str(p)]
    sound_start = image_start + len(stickers)
    for p in sounds:
        cmd += ["-i", str(p)]
    filters = [
        "[0:v]split=2[bg][fg]",
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=22:10[bg2]",
        "[fg]scale=980:1740:force_original_aspect_ratio=decrease[fg2]",
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[v0]"
    ]
    lastv = "v0"
    for i, e in enumerate(events):
        nxt = f"v{i+1}"
        start, end = max(0, e["time"]), min(duration, e["time"] + 2.2)
        filters.append(f"[{lastv}][{image_start+i}:v]overlay=(W-w)/2:1450:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]")
        lastv = nxt
    aud = "0:a" if has_audio else f"{silent}:a"
    filters.append(f"[{aud}]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a0]")
    lasta = "a0"
    for i, e in enumerate(events):
        nxt = f"a{i+1}"
        delay = int(e["time"] * 1000)
        filters.append(f"[{sound_start+i}:a]adelay={delay}|{delay},volume=0.75[s{i}]")
        filters.append(f"[{lasta}][s{i}]amix=inputs=2:duration=first:dropout_transition=0[{nxt}]")
        lasta = nxt
    target = 44 * 1024 * 1024
    vbps = max(64000, min(8000000, int(target * 8 / max(duration, 1)) - 128000))
    cmd += ["-filter_complex", ";".join(filters), "-map", f"[{lastv}]", "-map", f"[{lasta}]",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30",
            "-b:v", str(vbps), "-maxrate", str(vbps), "-bufsize", str(vbps*2),
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
    subprocess.run(cmd, check=True)
    if output.stat().st_size > MAX_UPLOAD:
        raise RuntimeError("Edited output exceeds Telegram's 50 MB bot upload limit. Original remains untouched.")

def send_result(token, chat, output, filename, count):
    caption = f"🔥 AI Roast Studio finished — {count} reaction(s). Original upload was not modified."
    with open(output, "rb") as f:
        r = requests.post(f"{API}/bot{token}/sendDocument",
                          data={"chat_id": chat, "caption": caption},
                          files={"document": (Path(filename).stem + "_roast.mp4", f, "video/mp4")},
                          timeout=(60, 600))
    r.raise_for_status()
    if not r.json().get("ok"):
        raise RuntimeError(f"Telegram delivery failed: {r.text}")

def main():
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    file_id = os.environ["TELEGRAM_FILE_ID"]
    filename = os.environ.get("ORIGINAL_FILENAME", "chat-recording.mp4")
    with tempfile.TemporaryDirectory(prefix="ai-roast-") as td:
        work = Path(td)
        source, output = work / "source.bin", work / "roast.mp4"
        size = download(token, file_id, source)
        say(token, chat, f"🎬 Video received ({size/1048576:.1f} MB). Editing a separate copy; original stays unchanged.")
        duration, has_audio = probe(source)
        events = scan(source, duration)
        render(source, output, events, duration, has_audio, work)
        send_result(token, chat, output, filename, len(events))
        print(f"Done: {duration:.1f}s, {len(events)} reaction(s), {output.stat().st_size} bytes")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
            try: say(token, chat, f"❌ AI Roast Studio could not process this video: {exc}")
            except Exception: pass
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

import asyncio
import time
from pathlib import Path

import edge_tts

DEFAULT_MALE_VOICE = "en-US-AndrewMultilingualNeural"


def make_voice(text: str, output_path: Path, config: dict):
    """Create validated male narration with retried Edge TTS and Google TTS fallback."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("Narration text is empty; refusing to create a silent audio file.")

    voice = str(config.get("voice") or DEFAULT_MALE_VOICE)
    rate = str(config.get("speech_rate") or "+0%")
    language = str(config.get("tts_fallback_language") or "en")
    output_path = Path(output_path)

    def validate_audio(provider: str):
        if not output_path.is_file() or output_path.stat().st_size < 1000:
            raise RuntimeError(f"{provider} produced an empty or incomplete audio file.")
        # FFprobe is present in the video workflows; use it when available to
        # reject truncated or non-audio files before they reach the renderer.
        import shutil
        import subprocess
        if shutil.which("ffprobe"):
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                 str(output_path)],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode != 0 or "audio" not in probe.stdout.lower():
                raise RuntimeError(f"{provider} output failed audio-stream validation: {probe.stderr[-500:]}")

    async def run():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        last_error = None
        for attempt in range(1, 6):
            try:
                output_path.unlink(missing_ok=True)
                print(
                    f"Generating narration with Edge TTS voice {voice} "
                    f"(attempt {attempt}/5; {len(text.split())} words)...",
                    flush=True,
                )
                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
                await asyncio.wait_for(communicate.save(str(output_path)), timeout=240)
                validate_audio("Edge TTS")
                print(f"Edge TTS narration validated ({output_path.stat().st_size} bytes).", flush=True)
                return
            except Exception as exc:
                last_error = exc
                output_path.unlink(missing_ok=True)
                if attempt < 5:
                    delay = min(30, 2 ** attempt)
                    print(f"Edge TTS attempt {attempt}/5 failed: {type(exc).__name__}: {exc}; retrying in {delay}s.", flush=True)
                    await asyncio.sleep(delay)

        print(
            f"Edge TTS failed after 5 attempts using {voice!r}: {last_error}. "
            "Switching to Google TTS fallback.",
            flush=True,
        )
        from gtts import gTTS
        fallback_error = None
        for attempt in range(1, 4):
            try:
                output_path.unlink(missing_ok=True)
                gTTS(text=text, lang=language, slow=False, timeout=(15, 90)).save(str(output_path))
                validate_audio("Google TTS")
                print(
                    f"Google TTS fallback validated ({output_path.stat().st_size} bytes; "
                    f"attempt {attempt}/3).",
                    flush=True,
                )
                return
            except Exception as exc:
                fallback_error = exc
                output_path.unlink(missing_ok=True)
                if attempt < 3:
                    delay = attempt * 5
                    print(
                        f"Google TTS attempt {attempt}/3 failed: {type(exc).__name__}: {exc}; "
                        f"retrying in {delay}s.",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
        raise RuntimeError(
            "Narration generation failed: Edge TTS exhausted 5 attempts and "
            f"Google TTS exhausted 3 attempts. Edge error: {last_error}; "
            f"Google TTS error: {fallback_error}"
        ) from fallback_error

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        # A separate thread avoids nesting an event loop in notebooks/async hosts.
        import threading
        errors = []
        def runner():
            try:
                asyncio.run(run())
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]

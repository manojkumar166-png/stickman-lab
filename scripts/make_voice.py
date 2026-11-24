import asyncio
from pathlib import Path

import edge_tts

DEFAULT_MALE_VOICE = "en-US-AndrewMultilingualNeural"
FALLBACK_MALE_VOICE = "en-US-GuyNeural"
# Only accept known male voices from configuration; never fall back to gTTS,
# whose voice gender cannot be selected reliably.
ALLOWED_MALE_VOICES = {
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-GuyNeural",
    "en-US-DavisNeural",
    "en-US-TonyNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-US-RogerNeural",
    "en-US-SteffanNeural",
}


def make_voice(text: str, output_path: Path, config: dict):
    """Create validated male narration using two Edge TTS male voices, five tries each."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("Narration text is empty; refusing to create a silent audio file.")

    configured_voice = str(config.get("voice") or DEFAULT_MALE_VOICE)
    voice = configured_voice if configured_voice in ALLOWED_MALE_VOICES else DEFAULT_MALE_VOICE
    configured_fallback = str(config.get("fallback_voice") or FALLBACK_MALE_VOICE)
    fallback_voice = (
        configured_fallback
        if configured_fallback in ALLOWED_MALE_VOICES and configured_fallback != voice
        else FALLBACK_MALE_VOICE
    )
    if fallback_voice == voice:
        fallback_voice = "en-US-BrianMultilingualNeural"
    rate = str(config.get("speech_rate") or "+0%")
    output_path = Path(output_path)

    def validate_audio(provider: str):
        if not output_path.is_file() or output_path.stat().st_size < 1000:
            raise RuntimeError(f"{provider} produced an empty or incomplete audio file.")
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
                raise RuntimeError(
                    f"{provider} output failed audio-stream validation: {probe.stderr[-500:]}"
                )

    async def try_voice(selected_voice: str) -> Exception | None:
        last_error = None
        for attempt in range(1, 6):
            try:
                output_path.unlink(missing_ok=True)
                print(
                    f"Generating male narration with Edge TTS voice {selected_voice} "
                    f"(attempt {attempt}/5; {len(text.split())} words)...",
                    flush=True,
                )
                communicate = edge_tts.Communicate(
                    text=text, voice=selected_voice, rate=rate
                )
                await asyncio.wait_for(communicate.save(str(output_path)), timeout=240)
                validate_audio(f"Edge TTS ({selected_voice})")
                print(
                    f"Male Edge TTS narration validated with {selected_voice} "
                    f"({output_path.stat().st_size} bytes).",
                    flush=True,
                )
                return None
            except Exception as exc:
                last_error = exc
                output_path.unlink(missing_ok=True)
                if attempt < 5:
                    delay = min(30, 2 ** attempt)
                    print(
                        f"Edge TTS {selected_voice} attempt {attempt}/5 failed: "
                        f"{type(exc).__name__}: {exc}; retrying in {delay}s.",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
        return last_error

    async def run():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        primary_error = await try_voice(voice)
        if primary_error is None:
            return

        print(
            f"Primary male voice {voice!r} failed after 5 attempts: {primary_error}. "
            f"Trying alternate male voice {fallback_voice!r}.",
            flush=True,
        )
        fallback_error = await try_voice(fallback_voice)
        if fallback_error is None:
            return

        raise RuntimeError(
            "Male narration generation failed: both Edge TTS male voices exhausted "
            f"5 attempts each. Primary ({voice}) error: {primary_error}; "
            f"fallback ({fallback_voice}) error: {fallback_error}. "
            "No female or Google gTTS fallback was used."
        ) from fallback_error

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
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

import asyncio
from pathlib import Path
import edge_tts


def make_voice(text: str, output_path: Path, config: dict):
    """Generate narration with retries and alternate Microsoft Edge voices."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    primary_voice = config.get("voice", "en-US-AriaNeural")
    voices = list(dict.fromkeys([
        primary_voice,
        "en-US-GuyNeural",
        "en-US-JennyNeural",
    ]))
    rate = config.get("speech_rate", "+0%")
    last_error = None

    async def run():
        nonlocal last_error
        for voice in voices:
            for attempt in range(1, 4):
                # Never leave a failed/partial audio file looking like success.
                try:
                    output_path.unlink(missing_ok=True)
                    communicate = edge_tts.Communicate(
                        text=text,
                        voice=voice,
                        rate=rate,
                    )
                    await communicate.save(str(output_path))
                    if output_path.exists() and output_path.stat().st_size >= 1000:
                        print(f"Narration generated with {voice} (attempt {attempt}).")
                        return
                    raise RuntimeError("TTS returned an empty or unexpectedly small audio file.")
                except Exception as exc:
                    last_error = exc
                    output_path.unlink(missing_ok=True)
                    print(
                        f"TTS failed for {voice} (attempt {attempt}/3): "
                        f"{type(exc).__name__}: {exc}"
                    )
                    if attempt < 3:
                        await asyncio.sleep(attempt * 2)
        raise RuntimeError(
            "Narration failed with all configured Edge TTS voices after retries. "
            "Check GitHub Actions network access and the Edge TTS service."
        ) from last_error

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        # Support callers that already have an active event loop.
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

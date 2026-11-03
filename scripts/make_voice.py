import asyncio
import time
from pathlib import Path

import edge_tts


def make_voice(text: str, output_path: Path, config: dict):
    """Generate narration with Edge TTS and retry transient service failures."""
    voice = config.get("voice", "en-US-AriaNeural")
    rate = config.get("speech_rate", "+0%")

    async def run():
        last_error = None
        for attempt in range(1, 6):
            try:
                # Remove a partial file left by an interrupted TTS request.
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.unlink(missing_ok=True)
                print(
                    f"Generating narration with Edge TTS (attempt {attempt}/5; "
                    f"{len(text.split())} words)...",
                    flush=True,
                )
                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
                await asyncio.wait_for(communicate.save(str(output_path)), timeout=240)
                if not output_path.exists() or output_path.stat().st_size < 1000:
                    raise RuntimeError("Edge TTS produced no usable narration audio.")
                print(
                    f"Narration generated successfully ({output_path.stat().st_size} bytes).",
                    flush=True,
                )
                return
            except Exception as exc:
                last_error = exc
                output_path.unlink(missing_ok=True)
                if attempt == 5:
                    break
                delay = min(30, 2 ** attempt)
                print(f"Edge TTS attempt {attempt}/5 failed: {exc}. Retrying in {delay}s.", flush=True)
                await asyncio.sleep(delay)
        raise RuntimeError(
            f"Edge TTS failed after 5 attempts using voice {voice!r}: {last_error}"
        ) from last_error

    try:
        asyncio.run(run())
    except RuntimeError as exc:
        # Preserve compatibility when called from an environment with a running loop.
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()

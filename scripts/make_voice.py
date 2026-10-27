import asyncio
from pathlib import Path
import edge_tts

def make_voice(text: str, output_path: Path, config: dict):
    async def run():
        communicate = edge_tts.Communicate(
            text=text,
            voice=config.get("voice","en-US-AriaNeural"),
            rate=config.get("speech_rate","+0%")
        )
        await communicate.save(str(output_path))
    try:
        asyncio.run(run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try: loop.run_until_complete(run())
        finally: loop.close()
    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError("Narration file was not generated or is unexpectedly small.")

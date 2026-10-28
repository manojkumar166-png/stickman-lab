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

    max_retries = 3
    for attempt in range(max_retries):
        try:
            asyncio.run(run())
            if output_path.exists() and output_path.stat().st_size > 1000:
                print(f"Voice generated successfully on attempt {attempt + 1}")
                return
            else:
                print(f"Attempt {attempt + 1} failed: File too small or missing.")
        except Exception as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
        
        if attempt < max_retries - 1:
            print("Waiting 5 seconds before retrying...")
            import time
            time.sleep(5)
    
    raise RuntimeError("Failed to generate voice after multiple retries. Microsoft TTS service may be temporarily down.")
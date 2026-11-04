import asyncio
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import edge_tts


def _make_edge_voice(text: str, output_path: Path, config: dict) -> None:
    async def run():
        communicate = edge_tts.Communicate(
            text=text,
            voice=config.get("voice", "en-US-AriaNeural"),
            rate=config.get("speech_rate", "+0%"),
        )
        await communicate.save(str(output_path))

    try:
        asyncio.run(run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run())
        finally:
            loop.close()


def _make_chatterbox_voice(text: str, output_path: Path, reference_url: str) -> None:
    try:
        import torch
        import torchaudio
        from chatterbox.tts import ChatterboxTTS
    except ImportError as exc:
        raise RuntimeError(
            "Chatterbox is selected but its dependencies are not installed. "
            "Set CHATTERBOX_REFERENCE_AUDIO_URL in GitHub Actions Secrets to enable installation."
        ) from exc

    with tempfile.TemporaryDirectory(prefix="chatterbox-") as temp_dir:
        temp = Path(temp_dir)
        reference_path = temp / "voice-reference"
        wav_path = temp / "narration.wav"

        request = urllib.request.Request(
            reference_url,
            headers={"User-Agent": "stickman-lab-github-actions"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            with reference_path.open("wb") as target:
                target.write(response.read())

        if reference_path.stat().st_size < 1000:
            raise RuntimeError("Downloaded Chatterbox reference audio is empty or too small.")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading Chatterbox on {device}...")
        model = ChatterboxTTS.from_pretrained(device=device)
        audio = model.generate(text, audio_prompt_path=str(reference_path))
        torchaudio.save(str(wav_path), audio.cpu(), model.sr)

        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", str(wav_path),
                "-codec:a", "libmp3lame", "-q:a", "2", str(output_path),
            ],
            check=True,
        )


def make_voice(text: str, output_path: Path, config: dict):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    engine = str(config.get("voice_engine", "edge_tts")).lower()

    if engine == "chatterbox":
        reference_url = os.getenv("CHATTERBOX_REFERENCE_AUDIO_URL", "").strip()
        if not reference_url:
            raise RuntimeError(
                "voice_engine is 'chatterbox' but CHATTERBOX_REFERENCE_AUDIO_URL "
                "is not configured in GitHub Actions Secrets."
            )
        _make_chatterbox_voice(text, output_path, reference_url)
    elif engine == "edge_tts":
        _make_edge_voice(text, output_path, config)
    else:
        raise ValueError(f"Unsupported voice_engine: {engine!r}")

    if not output_path.exists() or output_path.stat().st_size < 1000:
        raise RuntimeError("Narration file was not generated or is unexpectedly small.")

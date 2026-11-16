#!/usr/bin/env python3
"""Generates audio.wav from timeline events or silent fallback."""
import subprocess
from pathlib import Path


def main():
    # A per-film audio mixer can replace this fallback.
    # If no audio source exists, create a silent track.
    out = Path("audio.wav")
    if out.exists():
        return
    print("Generating fallback silent audio track...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "10", str(out),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()

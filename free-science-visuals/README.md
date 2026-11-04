# Free Science Visuals

Self-contained project workspace for generating science-video visuals using Wikimedia Commons, Pillow and optional local Blender rendering.

## Project layout

```text
free-science-visuals/
├── free_science_video.py       # Project entry point
├── config.json                 # Shared rendering/story settings
├── requirements.txt            # Python dependencies
├── topics.txt                  # Topic inspiration library
├── free_topic_history.json     # This workflow's topic history
└── scripts/
    ├── generate_story.py
    ├── free_visuals.py
    ├── render_3d_stills.py
    ├── blender_science_stills.py
    ├── make_voice.py
    └── render_video.py
```

## Run locally

```bash
python -m pip install -r requirements.txt
python free_science_video.py
```

Requires FFmpeg/ffprobe and `GEMINI_API_KEY`. Blender is optional; the renderer falls back to the Pillow/Wikimedia image pipeline when Blender is unavailable.

## Workflow safety

The existing GitHub Actions workflow continues to use its original paths under `science-channel/` and the repository root. Those production paths are deliberately unchanged in this organisation pass. Keep them until a separately tested workflow migration is approved.

Keep generated videos, scene images and temporary output under an ignored `output/` directory.

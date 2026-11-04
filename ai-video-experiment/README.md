# AI Video Experiment

Standalone home for the AI-generated science-video experiment.

## Project layout

```text
ai-video-experiment/
├── main_ai.py                 # Main generation entry point
├── cloudflare-worker.js       # Cloudflare Worker integration
├── config.json                # Video, narration and scene settings
├── requirements.txt           # Python dependencies
├── topic_history.json         # Topic history for this experiment
└── scripts/
    ├── generate_story.py
    ├── make_art.py
    ├── make_voice.py
    ├── free_visuals.py
    ├── render_3d_stills.py
    ├── blender_science_stills.py
    ├── render_video.py
    └── render_video_hybrid.py
```

## Run locally

From this directory, install dependencies and run:

```bash
python -m pip install -r requirements.txt
python main_ai.py
```

Requires FFmpeg/ffprobe and the `GEMINI_API_KEY` environment variable. Add any provider credentials required by optional integrations through environment variables; never commit secrets.

## GitHub Actions compatibility

The current production workflow still uses the repository-root compatibility files. They are intentionally retained so this organisation-only change does not alter workflow entry points or scheduled runs. The files in this folder are the project-local, organised copy. Do not delete the root compatibility files until a separately reviewed workflow migration is completed.

Generated media and temporary checkpoints belong in an ignored local `output/` directory, not in source control.

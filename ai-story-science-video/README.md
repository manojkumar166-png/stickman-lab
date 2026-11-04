# AI Story Science Video

Standalone Gemini-planned science documentary and animated-story generator.

## Project layout

```text
ai-story-science-video/
├── ai_story_video.py       # Story planner, narration and rendering pipeline
├── topics.txt              # Topic inspiration library
└── used_story_topics.json  # Previously used topics
```

## Run locally

Install the dependencies used by the generator:

```bash
python -m pip install -r requirements.txt
python ai_story_video.py --topic "" --scenes 48 --voice "en-US-AndrewMultilingualNeural"
```

Requires `GEMINI_API_KEY`, FFmpeg/ffprobe, and network access for Gemini and narration/image services.

## Workflow safety

The current production workflow still invokes `scripts/ai_story_video.py` from the repository root. That compatibility entry point is intentionally retained and unchanged. This folder contains the organised project-local copy; do not remove the original until a separately reviewed workflow migration is complete.

Generated files are written to `ai-story-video-output/` and should not be committed.

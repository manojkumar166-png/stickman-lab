# Storybook science visuals (no AI image generation)

The GitHub Actions workflows render original, hand-authored 2D storybook scenes using HTML/CSS and JavaScript in headless Chromium. Python plans and coordinates the scenes, generates narration through the existing story pipeline, and FFmpeg assembles the video.

## Secrets

- `GEMINI_API_KEY`: used only by the existing story-text planner.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: optional, for the daily workflow's Telegram delivery.

No image-generation API, Cloudflare credentials, paid visual service, 3D renderer, or external image asset is required for scene rendering.

## Run it

Open **Actions → Free Science Visuals — Storybook 2D → Run workflow** or **Daily Stickman Science Video — Storybook 2D → Run workflow**.

## Visual pipeline

1. Python prepares the story and scene descriptions.
2. `scripts/storybook_scene_renderer.py` renders layered scenery and topic-specific science motifs using HTML/CSS/JavaScript and Chromium.
3. Python and FFmpeg assemble the stills with narration into the final MP4.

The art direction is an original, Ghibli-inspired storybook atmosphere (lush landscapes, soft light, painterly color and wonder), not copied film frames or characters. The current renderer is an initial procedural scene system; inspect its output before merging or relying on it for production quality.

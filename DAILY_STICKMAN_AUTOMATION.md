# Daily Gemini Stickman Film Automation

This workflow adds a separate topic-to-video pipeline. It does not replace the existing cinematic or original-engine workflows.

## One-time setup

1. Create a Gemini API key in Google AI Studio.
2. In this GitHub repository, open **Settings → Secrets and variables → Actions → New repository secret**.
3. Add a secret named **GEMINI_API_KEY**. Do not commit the key to the repository.
4. Merge the pull request that adds this workflow.

## Schedule and manual runs

- The scheduled run starts daily at **09:00 Asia/Kolkata** (03:30 UTC).
- To run it manually, open **Actions → Daily Gemini Stickman Film → Run workflow**.
- Leave the optional topic blank to let Gemini choose a fresh topic. Enter a topic to override the automatic choice for that run.

## Production pipeline

1. Gemini 2.5 Flash creates a validated JSON brief with nine timed scenes.
2. The renderer turns the brief into a consistent 1920×1080 2D stickman animation.
3. Chromium renders nine preview stills and the complete 30-second film.
4. FFmpeg encodes H.264 video and the existing repository sound mixer adds sound effects (no music or voiceover).
5. ffprobe verifies codec, resolution, frame rate and duration. The workflow fails if the checks do not pass.
6. The MP4, film brief, contact sheet, preview stills and audit report are uploaded as a 30-day Actions artifact.
7. The workflow commits the title history to avoid repeating recent topics.

## Output

Open the successful workflow run and download the artifact named `daily-stickman-film-<run number>`. The MP4 is inside `stickman-films/latest/video.mp4`.

The daily workflow uses new files under `scripts/` and a new workflow file. Existing renderer scripts and workflows are left unchanged.

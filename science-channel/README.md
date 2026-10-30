# Independent Science Channel pipeline

This is an additive-only pipeline. It does not read, edit, import, or invoke the repository's existing workflows, topic files, scripts, or config.

## Workflow A — daily Gemini planner
`.github/workflows/science-channel-daily-planner.yml` runs daily and creates three episodes under `science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`. It uses only `science-channel/topics.txt` and `science-channel/history/generated-topics.json`. It first writes the full 47-scene narration script, then derives exactly 47 matching image prompts from that finalized script.

Required repository secret: `GEMINI_API_KEY`. Optional repository variable: `SCIENCE_GEMINI_MODEL` (defaults to `gemini-2.5-flash`).

## Manual Meta AI step
Generate the 47 prompts in `image-prompts.md` manually in Meta AI. Upload PNG files as `images/scene-001.png` through `images/scene-047.png`. Only after all 47 are present, add `READY.txt` to that episode folder and commit it.

## Workflow B — render ready episode
A push containing a READY.txt under the new episode directory starts the render workflow for that exact folder. It validates all 47 images and script sections, uses only `script.md` for narration/subtitles, and never reads `image-prompts.md`. Output is placed in that episode's `output/` directory and uploaded as a 14-day Actions artifact.

You can also run it manually with an exact `episode_path`.

## Independence guarantee
All new code and data live under `science-channel/`; the two workflow files have unique names. Existing workflow YAML, scripts, settings, topic files, secrets, and schedules are not modified. The render workflow has read-only repository permissions. The planner only commits under `science-channel/`.

## Notes
- The first render is a pilot; verify narration pacing, subtitle alignment, and output quality before relying on 3 episodes/day.
- Edge TTS is the existing low-friction voice option and depends on Microsoft's public service availability.
- Do not commit READY.txt until all 47 exact filenames have been uploaded.

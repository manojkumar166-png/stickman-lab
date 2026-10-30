# Independent Science Channel pipeline

This additive-only pipeline does not use or modify the repository's existing workflows, topic files, scripts, or shared config.

## Daily Gemini planner
The daily planner creates three episodes under `science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`. Gemini writes the complete narration first, as exactly 48 numbered scenes, then derives exactly 48 matching image prompts. It uses only `science-channel/topics.txt` and its own generated-topic history.

Required secret: `GEMINI_API_KEY`. Optional variable: `SCIENCE_GEMINI_MODEL`.

## Your image step — only three images
For each episode, copy the first three prompts from `image-prompts.md` into Meta AI. Upload exactly three image files (PNG, JPG, JPEG or WebP) into:

`images/incoming/`

You may keep any filenames. The renderer sorts filenames alphabetically and assigns them to scenes 001, 002 and 003. For predictable ordering, use names such as `1.png`, `2.png`, `3.png`.

## Render
After uploading the three images, add `READY.txt` to that exact episode folder and commit. The renderer uses the three uploads for scenes 1–3 and creates non-blank science-themed visual cards for scenes 4–48. Narration and subtitles are read from `script.md` only; `image-prompts.md` is never used for audio or subtitles. Outputs are uploaded as a 14-day GitHub Actions artifact.

You can also run the renderer manually by providing the exact `episode_path`.

## Isolation
All pipeline scripts, settings, topics, history and episode data live under `science-channel/`; the two workflow files have unique names. Existing workflow YAMLs, scripts, configs, topics, secrets, schedules and dependencies are left untouched.

# Independent Science Channel pipeline

This additive-only pipeline does not use or modify the repository's existing workflows, topic files, scripts, or shared config.

## Daily Gemini planner
The daily planner creates three episodes under `science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`. Gemini writes the complete narration first, as exactly 48 numbered scenes, then derives exactly 48 matching image prompts. It uses only `science-channel/topics.txt` and its own generated-topic history.

Required secret: `GEMINI_API_KEY`. Optional variable: `SCIENCE_GEMINI_MODEL`.

## Images: ZIP or individual files
For each episode, generate all 48 images from `image-prompts.md`. You can upload either:

- **One ZIP** containing exactly 48 PNG, JPG, JPEG or WebP images; or
- **48 individual image files**.

Place the ZIP or all individual images inside that episode's `images/incoming/` folder. The renderer accepts filenames such as `scene-001.png` through `scene-048.png`. If filenames contain scene numbers, it follows those numbers. If they do not, it sorts filenames alphabetically. Do not mix ZIPs and individual images in one upload.

## Render
Commit the images and `READY.txt` together in the exact episode folder. The render workflow validates 48 images and 48 script sections, normalizes images to 16:9, creates narration with Edge TTS, adds subtitles, and uploads the finished video as a 14-day GitHub Actions artifact.

You can also run it manually with the exact `episode_path`.

## Isolation
All pipeline scripts, settings, topics, history and episode data live under `science-channel/`; the two workflow files have unique names. Existing workflow YAMLs, scripts, configs, topics, secrets, schedules and dependencies are left untouched.

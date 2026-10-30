# Independent Science Channel pipeline

This additive-only pipeline is isolated to `science-channel/` and its two dedicated GitHub Actions workflows. It does not depend on or modify the repository's unrelated workflows, scripts, topic files, or shared configuration.

## Daily Gemini planner

The daily planner runs at **01:15 UTC (06:45 India Standard Time)** and creates **one episode per run** under:

`science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`

Gemini first writes a complete narration script with exactly 48 numbered scenes, then derives exactly 48 matching image prompts from that finalized script. Each episode package contains `episode.json`, `script.md`, `scenes.json`, `image-prompts.md`, and an empty `images/incoming/` folder.

The planner uses `science-channel/topics.txt`, its own generated-topic history, episode metadata, and the presenter reference for image-prompt consistency. Previously used topics are checked to reduce repeats.

Required GitHub secret: `GEMINI_API_KEY`. Optional repository variable: `SCIENCE_GEMINI_MODEL`.

Telegram prompt delivery uses `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. These are optional: if they are missing or Telegram delivery fails, the generated episode is still committed to the repository.

## Images: ZIP or individual files

For each episode, generate all 48 images from `image-prompts.md`. Upload either:

- **One ZIP** containing exactly 48 supported image files; or
- **48 individual image files**.

Supported image formats are PNG, JPG, JPEG, WebP, BMP, GIF, TIF, and TIFF. Place the ZIP or all individual images inside that episode's `images/incoming/` folder. Do not mix ZIP archives and individual images in the same incoming folder.

The renderer uses explicit scene numbers when it can identify a complete, unique sequence from 1 to 48 (for example, `scene-001.png`). Otherwise, it sorts filenames in natural order (so `image2` comes before `image10`).

## Render

Commit the 48 images and a `READY.txt` marker together in the exact episode folder. The render workflow validates the image count and the 48 ordered, non-empty script sections, converts the images to 16:9, generates narration with Edge TTS, and renders the video.

**Subtitles are intentionally not generated or added.**

The rendered output folder is uploaded as a GitHub Actions artifact named from the episode topic, with **2-day retention**. It includes the final MP4 and the renderer's supporting output files.

You can run the renderer manually from GitHub Actions. The optional `episode_path` input lets you specify the exact episode folder; if left blank, the workflow selects the newest episode with a READY marker or incoming images.

For automatic push-triggered rendering, upload or update exactly one episode per commit. The workflow stops with a clear error if a single push changes more than one episode, rather than silently rendering the wrong one.

After a successful render, the workflow attempts to delete a processed ZIP archive from the repository. Individual image files are not automatically deleted. ZIP cleanup retries up to three times.

## Isolation

All Science Channel scripts, settings, topics, history, and episode data remain under `science-channel/`. Only the two dedicated Science Channel workflow files are used for planning and rendering; unrelated repository workflows, scripts, configuration, and dependencies are left untouched.

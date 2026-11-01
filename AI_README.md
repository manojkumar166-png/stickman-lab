# AI Video Experiment — complete technical and customization guide

This guide covers the separate root-level **AI Video Experiment**. It is not the 48-scene Science Channel episode pipeline. The experiment uses Gemini for the story, Cloudflare Workers AI for scene images, Edge TTS for narration and FFmpeg for the MP4.

For the current episode-based pipeline, see [Science Channel operating guide](science-channel/README.md).

## 1. What the workflow does

Workflow file: `.github/workflows/ai-video-test.yml`

- Runs automatically every day at **05:30 UTC (11:00 India Standard Time)**.
- Can also be started manually from Actions → **AI Video Experiment** → Run workflow.
- Uses Python 3.11, installs FFmpeg and `requirements.txt`, then runs `python main_ai.py`.
- Generates a story using Gemini, creates scene illustrations using Cloudflare Workers AI, creates an MP3 narration with Edge TTS, and renders an MP4 with FFmpeg.
- Sends the MP4 to the configured Telegram chat, uploads the MP4 and story JSON as a GitHub Actions artifact retained for **7 days**, then commits `topic_history.json` to main.

**Important order:** Telegram delivery happens before artifact upload in this workflow. Unlike the Science Channel renderer, the Telegram step is not marked continue-on-error. If Telegram delivery fails, later artifact upload and topic-history commit steps may not run. Check the Actions log rather than assuming an artifact exists.

## 2. Files and what they control

| File | Purpose |
|---|---|
| `main_ai.py` | Orchestrates story generation, Cloudflare image generation, voiceover and video rendering. |
| `config.json` | Scene count, target duration, dimensions, FPS, preferred Gemini model, voice and speech rate. |
| `topics.txt` | Root pipeline's manual topic seed list. This is separate from `science-channel/topics.txt`. |
| `topic_history.json` | Previously generated root-pipeline topics, used to avoid exact repeats. |
| `scripts/generate_story.py` | Gemini story prompt, model fallback list, scene schema and topic-history logic. |
| `scripts/make_art.py` | Cloudflare model endpoint, image prompt/style, output dimensions and image fallback behavior. |
| `scripts/make_art_python.py` | Locally drawn stickman illustration fallback and its colors/backgrounds. |
| `scripts/make_voice.py` | Edge TTS voice and speech-rate handling. |
| `scripts/render_video.py` | FFmpeg video assembly, frame rate and encoding. |
| `.github/workflows/ai-video-test.yml` | Schedule, Actions permissions, secrets, Telegram delivery and artifact retention. |

Other entry points such as `main.py`, `main_gemini.py` and `main_hybrid.py` are separate local/experimental variants; the scheduled workflow specifically runs `main_ai.py`.

## 3. Current configuration

The root `config.json` currently contains:

| Setting | Current value | Meaning |
|---|---:|---|
| `target_minutes` | 8 | Target story length used in the Gemini prompt. |
| `scene_count` | 47 | Number of scenes requested from Gemini. |
| `width` / `height` | 1280 × 720 | Video dimensions (16:9). |
| `fps` | 24 | Video frame rate. |
| `gemini_model` | gemini-3.5-flash-lite | First Gemini model attempted; code also has a fallback list. |
| `voice` | en-US-AndrewMultilingualNeural | Edge TTS voice. |
| `speech_rate` | +0% | Normal speech rate. |
| `artifact_retention_days` | 7 | Documented config value; the Actions workflow currently sets artifact retention directly to 7 days in YAML. |
| `topic_history_file` | topic_history.json | Topic history file path. |
| `use_ai_art` | true | Configuration flag; the current `main_ai.py` explicitly runs the AI-art generation path. |

This configuration is independent of `science-channel/settings.json`. Changing the root `config.json` does not change Science Channel resolution, voice or scene count.

## 4. How to change the video

### Change narration voice or speed

Edit `config.json`:

```json
{
  "voice": "en-US-EmmaMultilingualNeural",
  "speech_rate": "-5%"
}
```

Use a valid Edge TTS voice name. Voice availability and language support can change; verify the voice before relying on it. The voice and rate are read by `scripts/make_voice.py`. A change affects future generated videos only.

### Change video duration and scene count

Edit `target_minutes` and `scene_count` in `config.json`. The story prompt in `scripts/generate_story.py` uses these values to request a target length and number of scenes.

The current prompt also requests roughly 28–32 spoken words per scene and about 1,200–1,350 words overall. Changing scene count or target duration may require adjusting that prompt so the total narration length remains sensible. More scenes mean more image-generation requests, longer workflow runtime and potentially greater provider usage.

The current scheduled workflow has a 60-minute timeout. Do not assume that a large scene-count increase will finish within it.

### Change resolution or frame rate

Edit `width`, `height` and `fps` in `config.json`. Keep width and height in the intended aspect ratio (currently 16:9). Higher resolution and FPS increase render time, compute and output size. Test locally before changing production settings.

### Change the Gemini text model

Edit `gemini_model` in `config.json`. The story generator tries the configured model first, then attempts its built-in fallback model list. The model must be available to the Gemini API key and support the request/JSON response format expected by `scripts/generate_story.py`.

To change provider (for example, from Gemini to another API), changing only the model string is not enough. Update the API URL, authentication, request body, response parsing and model fallback logic in `scripts/generate_story.py`, then test the returned JSON schema.

### Change the AI illustration style

Edit the `STYLE` string near the top of `scripts/make_art.py`. The current prompt asks for flat 2D vector-style educational illustrations with bold outlines, simple shapes, bright colors, a light background, no text and no photorealism.

For example, you can change the style prompt to request a paper-cut illustration, watercolor, 3D animation look or cinematic realism. Keep the description specific and consistent across scenes. The model may not follow every style instruction exactly.

### Change the Cloudflare image model

In `scripts/make_art.py`, find `CF_URL_CHEAP`. The current endpoint uses:

```text
@cf/black-forest-labs/flux-2-klein-4b
```

To use another Cloudflare model, check that model's current Workers AI documentation, accepted input fields and output format. Update the endpoint and, if needed, the request payload/response decoding in `cf_image_cheap()`. Not every image model accepts the same width/height fields or returns the same response format.

### Change the local stickman fallback

Edit `scripts/make_art_python.py`. Its `PALETTES` dictionary defines the scene background colors; `INK`, `SHIRT`, `PANTS`, `SKIN`, `WHITE` and `GOLD` define the main character/art colors. The drawing functions below these constants control scenery and character composition.

### Change topic seeds and writing style

Add one topic per line to the root `topics.txt`. The generator randomly chooses an unused seed topic (based on exact topic-history matching). When the list is exhausted, Gemini is asked to invent a new topic using the existing examples as style guidance.

To change the audience, tone, hook, narration structure, scene descriptions or JSON schema, edit the prompt in `scripts/generate_story.py`. If you change the JSON keys, update the downstream scripts that read those keys too.

The root pipeline's history is `topic_history.json`; it is separate from `science-channel/history/generated-topics.json`. Do not delete history unless you intentionally want old subjects to become eligible again. The root pipeline's matching is not the same semantic duplicate review used by the Science Channel planner.

## 5. Cloudflare image generation and fallback behavior

The active image-generation code is in `scripts/make_art.py`.

- It sends each scene's visual description plus the shared `STYLE` text to Cloudflare Workers AI.
- It requests 1024×576 images.
- It waits 6 seconds between scene requests.
- If an individual scene request fails but other images succeeded, the code fills that scene with a randomly selected successful image.
- If every AI image request fails, `main_ai.py` passes no AI image data to the artwork function, which falls back to locally drawn stickman illustrations through `make_art_python.py`.

This fallback behavior is not a promise that Cloudflare quota is unlimited or that every failed image will be unique. Inspect the generated scene images if image consistency matters. Do not remove the delay without checking the provider's current rate limits.

## 6. Topic history and output files

Generated files are placed under the root `output/` directory. The workflow reads the topic from the generated `output/story-*.json` file, sends the matching `output/ai-experiment-*.mp4` to Telegram, then uploads the MP4 and story JSON as the artifact named `ai-experiment-video`.

The workflow commits `topic_history.json` to main after artifact upload. If the run stops before that step, the latest topic may not be recorded in the repository history. Review the run logs and topic history if a run fails partway through.

## 7. GitHub Actions secrets and configuration

Open repository **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret | Required for | Description |
|---|---|---|
| `GEMINI_API_KEY` | Story generation | Google Gemini API key. |
| `CF_ACCOUNT_ID` | Cloudflare image generation | Cloudflare account ID. |
| `CF_API_TOKEN` | Cloudflare image generation | Cloudflare token with access to the required Workers AI endpoint. |
| `TELEGRAM_BOT_TOKEN` | Telegram video delivery | Token for the Telegram bot. |
| `TELEGRAM_CHAT_ID` | Telegram video delivery | Destination chat ID. |

Never paste secrets into source code, JSON, workflow inputs, README files or commits. If a token is exposed, revoke it and replace it in GitHub Secrets.

## 8. Change the schedule or artifact retention

Edit `.github/workflows/ai-video-test.yml`.

- The current cron is `30 5 * * *`, which is 05:30 UTC / 11:00 IST every day.
- Change the cron expression to change the schedule. GitHub cron uses UTC.
- The job timeout is currently 60 minutes.
- Artifact retention is currently set to `retention-days: 7` in the `Upload AI Video` step.
- The workflow requires `contents: write` to commit topic history.

Example cron values:
- `0 4 * * *` — daily at 04:00 UTC.
- `30 5 * * *` — daily at 05:30 UTC.
- `0 6 * * 1` — every Monday at 06:00 UTC.

Telegram delivery currently happens before artifact upload. If you want artifact upload to proceed even when Telegram is temporarily unavailable, change the Telegram step to `continue-on-error: true` or move artifact upload before Telegram, then test the resulting workflow behavior.

## 9. Run locally

Requirements: Python 3.11+, FFmpeg (including ffprobe), and packages from `requirements.txt`.

```bash
python -m pip install -r requirements.txt
python main_ai.py
```

Set the required environment variables in your shell before running:

- `GEMINI_API_KEY`
- `CF_ACCOUNT_ID`
- `CF_API_TOKEN`

For Telegram sending, the local script itself does not send the video; Telegram delivery is configured in the GitHub Actions workflow.

## 10. Troubleshooting

| Symptom | What to check |
|---|---|
| Missing Gemini key | Confirm `GEMINI_API_KEY` exists in Actions Secrets and is spelled exactly. |
| Gemini model/API error | Check model availability, API quota, key permissions and the model fallback messages in the log. |
| Cloudflare 401/403 | Check account ID, token permissions, endpoint and current Workers AI access. |
| Some repeated/mismatched scene images | Individual failed image requests can reuse another successful image; inspect logs and generated artwork. |
| All Cloudflare requests fail | The pipeline falls back to locally drawn stickman artwork. |
| FFmpeg not found | Confirm the workflow's FFmpeg install step completed; install FFmpeg locally for local runs. |
| Telegram step fails | Check bot token, chat ID, bot access to the chat and Telegram file-size/service limits. Since Telegram is before artifact upload, this may prevent the artifact step from running. |
| No artifact | Check whether the workflow reached the artifact upload step and whether the Telegram step succeeded. |
| Topic appears again | Check `topic_history.json` and whether the prior run reached the history commit step. |

## 11. Important separation from Science Channel

This is a separate 47-scene root generator. The Science Channel episode pipeline uses its own 48-scene setting, episode folders, topic history, Telegram image intake and render workflow. Do not change root `config.json`, root `topics.txt` or root `topic_history.json` expecting those changes to affect Science Channel episodes.

For the Science Channel's customization options, image upload methods, Telegram receiver, ZIP import, captions and rendering, read [science-channel/README.md](science-channel/README.md).

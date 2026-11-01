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


---

# ☁️ Cloudflare Workers AI — complete setup, configuration and troubleshooting

> **Scope:** Cloudflare is used by the separate root-level **AI Video Experiment** through `scripts/make_art.py`. The Science Channel episode pipeline currently does **not** use Cloudflare to generate its 48 scene images. Science Channel image creation is an external/manual stage; its Telegram workflows receive the images and the renderer assembles them.

## A. What Cloudflare does in this project

The AI Video Experiment asks Gemini to write the story and scene visual descriptions. For each scene, `main_ai.py` calls `generate_all_ai_images()` from `scripts/make_art.py`. That function sends a prompt to Cloudflare Workers AI using the model **`@cf/black-forest-labs/flux-2-klein-4b`**.

Current image-generation flow:

1. Gemini produces the scene list and each scene's `visual` description.
2. `build_prompt()` cleans the visual description, truncates it to 250 characters, and appends the shared `STYLE` instruction.
3. `cf_image_cheap()` sends one request per scene to Cloudflare.
4. The request asks for a 1024 × 576 image.
5. The code waits 6 seconds between scene requests to reduce request pressure.
6. Successful image bytes are collected in memory and passed back to the main pipeline.
7. Each image is resized to the configured video dimensions. The code draws a blue title strip and a black narration-caption strip over it.
8. If an individual scene request fails, the code reuses a randomly selected successful AI image for that scene. If every Cloudflare request fails, the pipeline uses the locally drawn stickman artwork from `scripts/make_art_python.py`.

**Important:** the current implementation is a single-model Cloudflare integration. Despite older references to multiple/cheap image models, the active code uses only FLUX-2-KLEIN-4B. It does not automatically switch to a second Cloudflare model.

## B. Create and configure Cloudflare credentials

You need a Cloudflare account with Workers AI access.

1. Sign in to the Cloudflare dashboard.
2. Find your Cloudflare account ID in the account overview/dashboard URL or account details.
3. Create an API token in the Cloudflare dashboard. Give it the minimum Workers AI permissions required by Cloudflare's current documentation for running AI models on the selected account. Do not use an unrestricted global API key if a scoped token is available.
4. In this GitHub repository, open **Settings → Secrets and variables → Actions → Secrets**.
5. Add these exact repository secret names:

| Secret name | Value | Used by |
|---|---|---|
| `CF_ACCOUNT_ID` | Your Cloudflare account identifier | Builds the Workers AI endpoint URL |
| `CF_API_TOKEN` | Your scoped Cloudflare API token | Authenticates each Workers AI request |

6. Save both values as **Secrets**, not Variables. They must never be committed to Git or placed in `config.json`, `README.md`, workflow inputs or source code.
7. Run **Actions → AI Video Experiment → Run workflow** to test the integration.

The workflow passes both secrets into the environment of the `python main_ai.py` step. Local runs must also export the same environment variables in the shell.

### Local environment example

Linux/macOS:

```bash
export CF_ACCOUNT_ID="your-account-id"
export CF_API_TOKEN="your-api-token"
export GEMINI_API_KEY="your-gemini-api-key"
python main_ai.py
```

PowerShell:

```powershell
$env:CF_ACCOUNT_ID="your-account-id"
$env:CF_API_TOKEN="your-api-token"
$env:GEMINI_API_KEY="your-gemini-api-key"
python main_ai.py
```

Use your real values locally; never paste them into a public issue, chat, commit or screenshot. If a token has been exposed, revoke it in Cloudflare and replace the GitHub secret.

## C. Exact API endpoint and request format

The endpoint is assembled in `scripts/make_art.py`:

```python
CF_URL_CHEAP = (
    f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
    "/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
)
```

The request is sent with Python `requests.post()` and these settings:

| Part | Current implementation |
|---|---|
| HTTP method | POST |
| Authentication | `Authorization: Bearer <CF_API_TOKEN>` |
| Content format | Multipart form data |
| `prompt` | Generated scene description plus shared style text |
| `width` | `1024` |
| `height` | `576` |
| Timeout | 120 seconds per request |
| Model | `@cf/black-forest-labs/flux-2-klein-4b` |

The code accepts either an image response (when the response content type begins with `image/`) or a JSON response containing a base64-encoded `image` field. It decodes the JSON image into bytes and returns those bytes to the image pipeline.

If you replace the model, check its current Cloudflare model page first. Do not assume another model accepts the same fields, returns the same response type, supports the same dimensions, or uses the same model identifier. You may need to update the endpoint, request payload, response decoder and image processing code together.

## D. Change the Cloudflare model

Edit `scripts/make_art.py`, find `CF_URL_CHEAP`, and replace the model identifier after `/ai/run/`.

Current model:

```text
@cf/black-forest-labs/flux-2-klein-4b
```

Before selecting a replacement:

- Confirm that the model is currently listed in Cloudflare Workers AI.
- Confirm it is available to your account and in your account's supported region/plan.
- Read its input schema: prompt field, width/height, guidance, seed and any other supported options.
- Read its output schema and content type.
- Check current pricing, free allocations, rate limits, concurrency and account quotas.
- Test one image before running a full 47-scene episode.

Then update the endpoint and any required request/response handling. A model name copied from a catalogue is not proof that the model is enabled for your account. Cloudflare changes its model catalogue and limits, so consult the official [Cloudflare Workers AI documentation](https://developers.cloudflare.com/workers-ai/) and [Workers AI models catalogue](https://developers.cloudflare.com/workers-ai/models/).

## E. Change image dimensions

In `cf_image_cheap()`, update the multipart values:

```python
"width": (None, "1024"),
"height": (None, "576")
```

The current 1024 × 576 request is 16:9. Keep a 16:9 ratio unless you intend to crop/pad the result later. The output is subsequently resized to the video width and height from root `config.json`; changing the request dimensions does not by itself change the final video resolution.

Check the selected model's permitted dimensions and multiples before increasing the size. Higher dimensions can increase latency, compute usage and failure rates. Test with one scene first.

## F. Change the art style and scene prompt

At the top of `scripts/make_art.py`, edit the `STYLE` string. Current style:

```python
STYLE = (
    "flat 2D vector illustration, educational explainer style, clean bold outlines, "
    "solid flat colors, limited bright palette, simple geometric shapes, "
    "plain light background, no gradients, no text, no photorealism"
)
```

Examples of style directions you can substitute:
- Hand-painted watercolor science illustrations.
- Paper-cut layered educational artwork.
- 3D animated educational scenes.
- Cinematic documentary concept art.
- Minimal monochrome technical diagrams.

Keep the style description consistent across all scenes. If you request text inside images, be aware image models often produce misspelled or distorted lettering; the current code separately draws a title and narration strip after generation.

The scene-specific part is created here:

```python
def build_prompt(visual):
    clean = " ".join(visual.split()).replace('"', "")[:250]
    return f"{clean}, {STYLE}"
```

The 250-character limit applies only to the scene's `visual` text before the shared style is appended. Increase or remove it only after considering model prompt limits and output consistency. The scene descriptions themselves are generated upstream in `scripts/generate_story.py`.

## G. Change the request pacing, timeout and failure handling

Inside `scripts/make_art.py`:

- `timeout=120` gives each Cloudflare request up to 120 seconds.
- `time.sleep(6)` waits six seconds between scene requests.
- There is no explicit retry/backoff loop for a failed image request.
- A failed scene is recorded as `None`.
- If at least one image succeeded, missing scenes reuse a random successful image.
- If no image succeeded, the main pipeline uses the local Python-drawn stickman scene art.

You can adjust the six-second delay or timeout, but do not remove the delay without checking Cloudflare's current rate limits. For a robust production change, implement bounded retries with exponential backoff for transient HTTP 429 and 5xx errors, while avoiding retries for permanent authentication or invalid-request errors. Log HTTP status and a safe error summary, but never log the bearer token or full authorization headers.

If you want a different fallback policy, change the section under `# If any failed, reuse a successful image to fill the gap`. For example, you could fail the entire job instead of repeating an image, or use local stickman artwork only for the failed scene. That requires changing how `main_ai.py` handles `None` image data and how the artwork function is called. Test the full pipeline after modifying this behavior.

## H. Change the title and narration strips drawn over images

The function `make_scene_art()` in `scripts/make_art.py` handles the final image composition:

- Resizes the generated image to the requested output dimensions.
- Draws a rounded blue title bar at the top.
- Uses the scene's `title`, truncated to 58 characters.
- Draws a black caption bar along the bottom.
- Wraps the scene narration into lines and displays at most two lines.
- Uses DejaVu Sans fonts from the system font folder.

To change these overlays, edit the drawing coordinates, colors, font sizes, title length and line-wrapping logic in `make_scene_art()`. The font helper `font()` loads DejaVu Sans or falls back to Pillow's default font if unavailable. The workflow must have the DejaVu font files installed for the intended appearance.

The bottom strip is a static scene caption, separate from any word-synchronized karaoke captions used in the Science Channel renderer.

## I. Cloudflare troubleshooting

| Error/symptom | Likely cause | What to check/change |
|---|---|---|
| `CF credentials missing` | One or both environment variables are empty | Add exact secrets `CF_ACCOUNT_ID` and `CF_API_TOKEN`; check workflow environment mapping. |
| HTTP 401 | Invalid, expired or revoked token | Create a new scoped token and update the secret. |
| HTTP 403 | Token lacks permission or account access | Check Workers AI permissions and account ID. |
| HTTP 404 / model not found | Incorrect model identifier or model no longer available | Verify current model catalogue and endpoint syntax. |
| HTTP 400 | Unsupported field, dimension or malformed prompt | Compare request fields with the selected model's current schema. |
| HTTP 429 | Rate limit or quota exceeded | Check account limits; add safe backoff/retry and retain pacing. |
| HTTP 5xx | Temporary service/model error | Retry a limited number of times with backoff; inspect Cloudflare status. |
| Request timeout | Slow generation or network issue | Check the 120-second timeout and model latency. |
| Response JSON has no `image` field | Model response format differs from current decoder | Inspect the documented response schema and update response parsing. |
| Some scenes repeat | Current fallback intentionally reuses a random successful image | Check the log for `Filled with a random AI image`; change fallback policy if required. |
| All images become stickman drawings | Every Cloudflare image request failed | Check credentials, model access, quota and response errors. |

---

# 📲 Telegram — complete bot setup, upload, delivery and modification guide

Telegram is used in **both pipelines**, but the responsibilities differ:

- **Science Channel:** Telegram can receive the 48 images, receive a ZIP, receive the planner's image-prompt document and receive the final rendered episode MP4.
- **AI Video Experiment:** Telegram receives the generated experiment MP4. It does not use the Science Channel image receiver.
- Both workflows use the repository secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. You can use one bot/chat for both, or configure a separate bot and chat if you deliberately change the workflow secrets.

## A. Create a Telegram bot

1. Open Telegram and search for the official **@BotFather** account.
2. Start a chat with BotFather.
3. Send `/newbot`.
4. Choose a display name, such as `Stickman Lab Science Bot`.
5. Choose a username ending in `bot`, for example `stickman_lab_science_bot` (the username must be available).
6. BotFather returns a bot token. Copy it privately. Anyone who has this token can control your bot.
7. Open the new bot's Telegram link and press **Start** once so a private chat exists.
8. Keep the bot token private; do not put it in the repository.

If you use a Telegram group instead of a private chat, add the bot to that group and ensure the bot can see the image/document messages. Group privacy settings can prevent bots from receiving ordinary group messages; a private chat with the bot is the simplest setup for image uploads.

## B. Find the chat ID and add GitHub secrets

The project filters incoming messages by exact chat ID and sends outgoing files to that same configured destination.

1. Send a message to your bot (for a group, send a message after adding the bot).
2. Use Telegram's Bot API `getUpdates` method with your bot token to inspect the update's `message.chat.id`. Keep the token private. Do not paste a tokenized API URL into a public browser, issue or chat.
3. Copy the numeric chat ID exactly. Group chat IDs are often negative; do not remove a minus sign.
4. In GitHub, open **Settings → Secrets and variables → Actions → Secrets**.
5. Create/update:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather.
   - `TELEGRAM_CHAT_ID` = numeric private-chat or group-chat ID.
6. Save both as repository **Secrets**.

The same names are referenced by the planner, receiver and video workflows. If the token is changed, update the one repository secret rather than editing Python or YAML files.

### How the code uses the credentials

The image receiver reads both environment variables in `science-channel/scripts/telegram_image_receiver.py`. The planner sends its prompt document with Telegram's `sendDocument` endpoint. The video workflows use the `PonomarevDA/telegram-upload@v1` GitHub Action with the same token and chat ID.

If you use different bots for different workflows, edit the relevant workflow secret references (for example `secrets.TELEGRAM_BOT_TOKEN`) to use separate secret names, then create those secrets in repository settings. Do not hardcode a token in a workflow file.

## C. Understand the Telegram Image Receiver workflow

Workflow: `.github/workflows/telegram-image-receiver.yml`

| Setting | Current behavior |
|---|---|
| Workflow name | Telegram Image Receiver |
| Schedule | Every 5 minutes (`*/5 * * * *`, UTC) |
| Manual run | Actions → Telegram Image Receiver → Run workflow |
| Branch | Checks out and pushes to `main` only |
| Runner | Ubuntu latest |
| Python | 3.11 |
| Timeout | 8 minutes |
| Python dependency | `requests` |
| Script | `science-channel/scripts/telegram_image_receiver.py` |
| Permissions | `contents: write` |
| Concurrency | Shares `science-channel-main-writer` with the planner; queued writes are not cancelled |

This is **polling**, not a permanently running bot server. The bot checks Telegram when the GitHub Actions job runs. A message may therefore wait until the next five-minute poll. GitHub scheduled jobs can start later than the exact cron minute. You can manually run the workflow to poll sooner.

### How incoming messages are processed

1. The workflow checks out the latest `main` branch.
2. The Python receiver loads `science-channel/telegram-bot-state.json`.
3. It reads the saved Telegram update offset and selected episode path.
4. It calls Telegram `getUpdates` for new messages.
5. It ignores messages whose `message.chat.id` does not exactly match `TELEGRAM_CHAT_ID`.
6. It handles `/start`, `/help` and `/episode` commands.
7. It downloads supported photos/documents using Telegram `getFile` and the file download endpoint.
8. It saves scene files under the selected episode's `images/incoming/` directory.
9. When scene numbers 01–48 are all present, it creates `READY.txt`.
10. The workflow commits episode uploads and `telegram-bot-state.json` to `main`. The push of images/READY marker triggers the renderer.

The bot's offset is important: it tells Telegram which updates have already been processed. Do not delete `science-channel/telegram-bot-state.json` casually. Resetting it may cause old Telegram updates to be read again, potentially duplicating or reprocessing messages.

## D. Bot commands and episode selection

| Command | What it does |
|---|---|
| `/start` | Sends the basic upload instructions. |
| `/help` | Sends the same help instructions. |
| `/episode 2026-11-01/episode-001` | Selects an existing episode folder already committed to `main`. |

Use the actual date and episode folder name returned by the planner. The accepted format is a date followed by `episode-NNN`; the episode must contain `episode.json` on the checked-out `main` branch.

If you do not select an episode, the receiver chooses the newest episode package it can find on `main`. When a newer episode package is published, the automatic newest-episode logic can replace an older selection. If you are uploading to an older episode while a newer episode exists, check the bot's selected-episode reply and the saved state carefully before sending all 48 images.

Messages from any other chat are ignored. The receiver does not act as a general-purpose Telegram file downloader.

## E. Send 48 individual images

1. Wait until the episode package exists on `main`.
2. Check that the bot has selected the intended episode. If necessary, send its `/episode` command.
3. Generate exactly 48 images, one per scene, in scene order.
4. Send them to the configured bot chat as Telegram photos or image documents.
5. The receiver fills the next missing scene number. The first accepted image becomes `scene-01`, the next missing slot becomes `scene-02`, and so on.
6. After each accepted image, the bot replies with the count received and the next missing scene number.
7. When all 48 scene numbers exist, it writes `READY.txt`. The workflow commits the images and the renderer starts from the new commit.

**Accepted individual formats:** JPG/JPEG, PNG and WebP. Telegram photo messages are saved as JPG. For document uploads, the receiver checks the filename extension and/or image MIME type. A document must resolve to one of the supported extensions.

**Size limits in the receiver:** a downloaded Telegram file larger than 50 MiB is rejected before processing. An individual non-ZIP image larger than 20 MiB is also rejected. Each image inside a ZIP must be no larger than 20 MiB.

Send images in the correct order. The receiver assigns the next missing scene slot based on arrival order; it does not read your intended scene number from the image's filename or caption. If you send scene 12 first, it will be stored as scene 01.

## F. Send one ZIP directly to the Telegram bot

1. Put exactly 48 supported image files in one ZIP archive.
2. Send the ZIP as a Telegram document to the configured bot chat.
3. The receiver reads supported image entries and sorts their archive filenames alphabetically (case-insensitive).
4. It requires exactly 48 supported images and rejects the ZIP if the episode already has any scene images.
5. It checks that each image is no larger than 20 MiB.
6. It writes the images as `scene-01` through `scene-48` in the episode's incoming folder.
7. It creates `READY.txt` after verifying that all 48 scene numbers exist.

The entire downloaded ZIP is rejected if it is larger than 50 MiB. The receiver does not use the ZIP's internal folder structure for output paths; it reads image entries and writes numbered scene files. Non-image entries are ignored. Use simple filenames such as `scene-01.png`, `scene-02.png`, etc. to ensure the intended order is clear.

**Do not mix methods:** send either 48 individual images or one ZIP for an empty episode. If any scene image already exists, the receiver skips a ZIP upload. The ZIP import route described below also refuses to overwrite existing images.

## G. Alternative: stage a ZIP in GitHub and run Telegram ZIP Import

Workflow: `.github/workflows/telegram-zip-import.yml`

This route does not require sending the ZIP through the bot, but the archive must first be committed into the repository.

1. On `main`, add the ZIP directly under `science-channel/telegram-uploads/`.
2. The filename can be any name ending in `.zip`, such as `dream.zip` or `48 scene images.zip`.
3. Open Actions → **Telegram ZIP Import** → Run workflow.
4. Enter `episode_path`, e.g. `science-channel/daily-episodes/2026-11-01/episode-001`.
5. Enter `zip_path`, e.g. `science-channel/telegram-uploads/dream.zip`.
6. Run the workflow.

Importer validation:

- Episode path must be inside `science-channel/daily-episodes/YYYY-MM-DD/` and contain `episode.json`.
- ZIP must be a direct child of `science-channel/telegram-uploads/`; nested staging paths are not accepted.
- ZIP file must be non-empty and at most 25 MiB.
- Archive must be a valid ZIP.
- Exactly 48 supported image entries are required: PNG, JPG/JPEG or WebP.
- Each image must be at most 20 MiB.
- Archive paths may not be absolute, contain `..` path traversal, or be symbolic links.
- Duplicate image basenames are rejected.
- Existing incoming images prevent import; the importer will not overwrite them.
- Images are sorted naturally by filename and renamed to `scene-01` through `scene-48`.

The workflow uses `GH_PAT` to authenticate checkout so it can push the imported image files. The token needs repository contents write permission. After extraction, the workflow commits the images and `READY.txt` to `main`, removes the staged ZIP from the repository and pushes the commit. That push triggers the renderer.

## H. How Telegram sends the planner prompts and finished videos

### Planner sends the image prompts

Workflow: `.github/workflows/science-channel-daily-planner.yml`

After the episode package has been committed and verified on `main`, the workflow calls Telegram's `sendDocument` endpoint to send `image-prompts.md` to the configured chat. The message includes the episode title and repository folder where the 48 images should be uploaded.

- Prompt delivery is configured as non-blocking (`continue-on-error: true`).
- If Telegram secrets are missing, the workflow skips sending the document.
- A Telegram prompt-send failure does not undo the episode package commit.

### Renderer sends the finished Science Channel MP4

Workflow: `.github/workflows/free-science-visuals.yml`

The renderer first creates the MP4 and uploads it as a GitHub Actions artifact (2-day retention). It then invokes `PonomarevDA/telegram-upload@v1` to send the MP4 to the configured chat.

- The video-send step is `continue-on-error: true`.
- If Telegram delivery succeeds, the workflow deletes all files in the episode's `images/incoming/` folder except `.gitkeep`, removes `READY.txt`, and pushes the cleanup commit to `main`.
- If Telegram delivery fails, cleanup is skipped and the source ZIP/images remain in the repository for retry.
- The artifact is uploaded before Telegram delivery, so it may be downloadable even if the Telegram send fails.
- Wait for the cleanup commit before uploading the same ZIP filename again.

### Legacy AI Video Experiment sends its MP4

Workflow: `.github/workflows/ai-video-test.yml`

This separate workflow also uses `PonomarevDA/telegram-upload@v1`, but sends `output/ai-experiment-*.mp4`. In the current YAML the Telegram step is **not** `continue-on-error` and comes before artifact upload. If Telegram sending fails, the job may stop before the artifact and topic-history steps. If you want the artifact to be preserved even when Telegram is unavailable, set `continue-on-error: true` on that step or move artifact upload before it, then test the workflow.

## I. Change Telegram behavior — exact files to edit

| Change | File | What to modify |
|---|---|---|
| Change bot token or chat | GitHub repository Secrets | Update `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; do not edit source code. |
| Change receiver poll frequency | `.github/workflows/telegram-image-receiver.yml` | Edit the `schedule.cron` value. Cron uses UTC. |
| Change receiver timeout/Python version | `.github/workflows/telegram-image-receiver.yml` | Edit `timeout-minutes` or `python-version`. |
| Change accepted Telegram image formats | `science-channel/scripts/telegram_image_receiver.py` | Edit `image_payload()` extension/MIME checks and ZIP suffix list. |
| Change individual image size limit | `science-channel/scripts/telegram_image_receiver.py` | Edit the `20 * 1024 * 1024` check. |
| Change Telegram ZIP download limit | `science-channel/scripts/telegram_image_receiver.py` | Edit the `50 * 1024 * 1024` downloaded-file check. |
| Change number of required images | Receiver script plus planner, importer, settings, renderer and workflows | This project assumes 48 throughout; do not edit only one place. |
| Change bot replies/commands | `science-channel/scripts/telegram_image_receiver.py` | Edit the `/start`, `/help`, `/episode` handling and `send()` messages. |
| Change episode auto-selection | `science-channel/scripts/telegram_image_receiver.py` | Edit `newest_episode()` and the selection logic in `main()`. |
| Change bot update persistence | `science-channel/scripts/telegram_image_receiver.py` and `science-channel/telegram-bot-state.json` | Review offset and selected episode behavior before resetting state. |
| Change ZIP staging folder or ZIP/image limits | `science-channel/scripts/import_telegram_zip.py` | Edit `STAGING_ROOT`, `ALLOWED`, `MAX_ZIP_BYTES`, `MAX_IMAGE_BYTES` and validation. Also update workflow inputs/docs if path changes. |
| Change the ZIP import's GitHub token | GitHub secret `GH_PAT` and `.github/workflows/telegram-zip-import.yml` | Keep token secret and checkout token mapping correct. |
| Change planner prompt document/caption | `.github/workflows/science-channel-daily-planner.yml` | Edit `sendDocument` curl fields and caption. |
| Change Science Channel video message | `.github/workflows/free-science-visuals.yml` | Edit the Telegram upload action's `message`. |
| Change legacy experiment video message | `.github/workflows/ai-video-test.yml` | Edit the `message` input of the Telegram upload action. |
| Change video delivery failure behavior | Relevant workflow YAML | Set `continue-on-error` or reorder steps; understand whether artifact/cleanup/history steps then run. |

### Change Telegram poll frequency example

The receiver currently polls every five minutes:

```yaml
schedule:
  - cron: "*/5 * * * *"
```

Examples:
- Every minute: `* * * * *` (more frequent Actions runs; may use more Actions minutes).
- Every 10 minutes: `*/10 * * * *`.
- Every 15 minutes: `*/15 * * * *`.

Keep the workflow's `workflow_dispatch` trigger if you still want to poll manually. Scheduled GitHub Actions are not guaranteed to start at the exact cron minute.

## J. Telegram troubleshooting

| Symptom | What to check |
|---|---|
| Bot never replies | Check that receiver workflow ran; it is a poller, not a continuously running process. Check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, workflow logs and bot access to the chat. |
| Bot replies in a different chat or ignores you | The incoming chat ID must exactly equal `TELEGRAM_CHAT_ID`. Group IDs may be negative. |
| Bot does not see group images | Use a private chat or review BotFather group privacy settings and bot membership/permissions. |
| `/episode` says not found | The episode must already exist on `main`, the date and `episode-NNN` must match, and the folder must contain `episode.json`. |
| Images go into the wrong episode | Check the bot's auto-selected episode reply and `science-channel/telegram-bot-state.json`; send the correct `/episode` command and verify selection before uploading. |
| An image is ignored | Check the file extension/MIME type; receiver accepts JPG/JPEG, PNG and WebP. Unsupported documents are ignored. |
| Image too large | Individual images must be at most 20 MiB; the overall Telegram download guard is 50 MiB. Compress or resize before sending. |
| ZIP says it needs 48 images | It must contain exactly 48 supported image entries. Remove extra image files or add missing ones. |
| ZIP is skipped because images exist | The Telegram receiver only imports a ZIP into an empty incoming folder. Remove/clean the previous upload or use a new empty episode. |
| Count stays below 48 | Check the incoming scene filenames; receiver counts `scene-01` through `scene-48` with JPG/PNG/WebP extensions. Check whether a file was rejected for size. |
| Images received but renderer does not start | Check that the receiver successfully committed to `main`, that the push included incoming files or `READY.txt`, and that the renderer workflow path filters match. |
| ZIP import fails | Check `GH_PAT`, exact `episode_path`/`zip_path`, ZIP staging directory, 25 MiB archive limit, 20 MiB per-image limit and exactly 48 valid images. |
| Video not delivered | Check token/chat secrets, bot permissions, Telegram service/file limits and the upload action logs. For Science Channel, download the artifact if already uploaded. |
| Same ZIP filename cannot be uploaded again | Wait until successful Telegram delivery and the cleanup commit have reached `main`; the staging path must no longer exist. |

## K. Security and operational rules

- Never expose `TELEGRAM_BOT_TOKEN`, `CF_API_TOKEN`, `GEMINI_API_KEY` or `GH_PAT`.
- Do not store bot tokens in `telegram-bot-state.json`; that file stores polling offset and episode selection, not credentials.
- Only the configured chat ID is processed by the receiver. This is a chat-level allowlist; protect access to that chat.
- The Science Channel receiver/importer/rendering and cleanup must stay on `main`. Do not point these workflows at `adaptive-cinematic-effects`.
- Do not change the expected image count in only one script. The whole episode pipeline assumes 48 scenes.
- Do not assume a successful Telegram upload means the video is permanently stored in GitHub artifacts. Download artifacts before their retention period expires.

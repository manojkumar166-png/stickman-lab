# Stickman Lab — automated science video production

This repository contains **two related but separate video pipelines**:

1. **Science Channel (episode workflow):** Gemini plans a new 48-scene episode, you review the narration and create its 48 images, and GitHub Actions renders the finished 8–10 minute video. Telegram can deliver prompts, receive images, and deliver the final MP4.
2. **AI Video Experiment:** a separate generator creates a narrated video using Gemini for the story and a resilient image-provider chain (Cloudflare, AI Horde and OVHcloud) for scene artwork.

The Science Channel pipeline is the current episode-based workflow. Its planning, Telegram upload, ZIP import, rendering and cleanup workflows operate on **main only**. Do not use the adaptive-cinematic-effects branch for Science Channel episodes or uploads.

---

## Start here: which workflow should I use?

| What you want to do | GitHub Actions workflow | How it starts |
|---|---|---|
| Create a new Science Channel episode and its 48 image prompts | **Science Channel — Daily Gemini Planner** | Daily schedule or manual |
| Send 48 scene images to the bot, one by one or as one ZIP | **Telegram Image Receiver** | Cloudflare Worker webhook forwards uploads; can also be run manually |
| Import a ZIP uploaded into the repository's staging folder | **Telegram ZIP Import** | Manual; you provide the episode folder and ZIP path |
| Turn an episode's 48 images into a final MP4 | **Free Science Visuals — Render Ready Episode** | Push of incoming files / READY marker, or manual |
| Run the separate Cloudflare AI-art experiment | **AI Video Experiment** | Daily schedule or manual |
| Create a standalone 48-scene Gemini story/science video with free anonymous image providers | **AI Story & Science Video Creator** | Manual; one click, no inputs |
| Check workflow YAML, Python entry points and Cloudflare Worker syntax | **Validate Workflows** | Repository code/workflow changes |

There are **eight active workflow files** in `.github/workflows/` (including the workflow validator). Each active workflow now has a dedicated detailed guide linked from [`.github/workflows/README.md`](.github/workflows/README.md). The AI Video Experiment's dedicated setup and customization guide is in [ai-video-experiment/README.md](ai-video-experiment/README.md). The old README references to daily-video.yml and gemini-video.yml were incorrect; those files are not the active workflows in this repository.

## Workflow map and detailed behavior

### 1. Science Channel — Daily Gemini Planner
**Topic-generation approach:** each run randomly chooses one broad science category and asks Gemini to create a new, accessible curiosity-driven question within it. The planner reads `science-channel/topics.txt` as a **style reference, not a fixed topic list**. It aims for clear questions like “Why do we get goosebumps?” or “How do bees communicate?”—but generates new subjects rather than copying these examples. Gemini is instructed to consider at least 10 candidates internally, select the strongest idea for an 8–10 minute episode, and avoid manufactured drama or complicated clickbait. Exact and semantic duplicate checks compare proposed ideas against topic history and existing episode metadata. See [the complete Science Channel operating guide](science-channel/README.md#how-topic-selection-works).


File: [.github/workflows/science-channel-daily-planner.yml](.github/workflows/science-channel-daily-planner.yml)

- **Automatic schedule:** every day at 01:15 UTC (06:45 India Standard Time).
- **Manual start:** Actions → Science Channel — Daily Gemini Planner → Run workflow. Select main.
- **What it does:** calls Gemini to select one fresh, broad-interest science topic, writes the episode metadata and narration, creates 48 numbered scene records, and generates 48 matching image prompts.
- **Topic repetition protection:** checks the saved topic history and existing episode metadata. It rejects exact/title-similar and semantically overlapping subjects; accepted topics are reserved in the history before the package is built.
- **What it commits:** a new folder under science-channel/daily-episodes/YYYY-MM-DD/episode-NNN-topic/, including episode.json, script.md, scenes.json, image-prompts.md and images/incoming/.gitkeep. It also commits science-channel/history/generated-topics.json.
- **Telegram:** after the episode has been committed and verified on main, it optionally sends image-prompts.md to Telegram. Missing Telegram secrets or prompt-delivery failure do not undo the episode commit.
- **What it does not do:** it does not create the 48 images and does not render a video. You create/review the images and then submit them using one of the upload routes below.

The schedule is in UTC. GitHub Actions scheduled runs can start later than the exact cron minute during periods of high GitHub load.

### 2. Telegram Image Receiver

File: [.github/workflows/telegram-image-receiver.yml](.github/workflows/telegram-image-receiver.yml)

- **Automatic intake:** the Cloudflare Worker receives Telegram webhook updates and forwards image/ZIP uploads and /episode selections to this workflow by saving each update in a durable GitHub inbox.
- **Manual start:** Actions → Telegram Image Receiver → Run workflow is available for maintenance, but normal Telegram intake is webhook-driven.
- **Branch:** checks out and commits only to main.
- **Episode selection:** by default it automatically selects the newest episode package currently present on main. To select a different existing episode, send the bot the exact folder name, for example /episode 2026-11-01/episode-001-topic-slug. The episode must already exist on main.
- **Accepted uploads:** send 48 individual image files/photos, or send one ZIP containing exactly 48 supported images. Supported receiver formats are JPG/JPEG, PNG and WebP. The bot numbers individual images into the next available scene slot; a ZIP is sorted and expanded into scene files.
- **Completion:** once all 48 scene slots are present, the receiver creates READY.txt. The workflow commits received files, receiver state and processed-inbox deletions to main, then explicitly dispatches the renderer for that exact episode.
- **Telegram commands:** /start and /help show instructions; /episode YYYY-MM-DD/episode-NNN selects an existing main-branch episode.
- **Important:** send uploads to the configured bot chat. The receiver only accepts messages from the configured TELEGRAM_CHAT_ID. A ZIP must contain exactly 48 images and cannot be mixed with already-uploaded scene images. For ZIP uploads, the original archive is retained as images/incoming/source-upload.zip until Telegram confirms delivery; it is then deleted with the extracted images.

This is the easiest route when you want to send images directly from Telegram. The receiver does not poll Telegram. The Cloudflare Worker owns the Telegram webhook and forwards upload updates to this workflow; this prevents webhook/polling conflicts.

### 3. Telegram ZIP Import (repository staging route)

File: [.github/workflows/telegram-zip-import.yml](.github/workflows/telegram-zip-import.yml)

Use this route when you first upload a ZIP file to the repository rather than sending it to the bot.

1. Upload the ZIP directly into science-channel/telegram-uploads/ on main. The filename can be anything ending in .zip, for example dream.zip, my-scene-images.zip or Telegram Upload.zip.
2. Open Actions → Telegram ZIP Import → Run workflow.
3. Enter the exact episode folder in episode_path, for example science-channel/daily-episodes/2026-11-01/episode-001.
4. Enter the repository path of the ZIP in zip_path, for example science-channel/telegram-uploads/dream.zip.
5. Start the workflow.

The importer validates the episode and ZIP, requires exactly 48 supported image files, rejects unsafe archive paths and oversized files, extracts and numbers the images in that episode's images/incoming/ folder, creates READY.txt, and preserves a copy of the original archive there as source-upload.zip. It removes the staging copy from science-channel/telegram-uploads/ and commits the extracted images, retained source ZIP and READY marker to main. The resulting commit starts the renderer.

**ZIP naming rules:** the filename is not fixed; any .zip name is accepted. The ZIP must be directly inside science-channel/telegram-uploads/ (not a nested folder), and the archive itself must be valid and contain exactly 48 supported images. The ZIP is limited to 25 MB and each image to 20 MB.

**Required secret:** GH_PAT. It must be a personal access token with permission to write repository contents, because this workflow pushes the extracted files to main. Do not paste the token into a workflow input or commit it to the repository.

### 4. Free Science Visuals — Render Ready Episode

File: [.github/workflows/free-science-visuals.yml](.github/workflows/free-science-visuals.yml)

- **Automatic trigger:** a push to main that adds or changes real files under an episode's images/incoming/ directory, or changes that episode's READY.txt. The .gitkeep placeholder alone is ignored.
- **Manual start:** Actions → Free Science Visuals — Render Ready Episode → Run workflow. You may enter the exact episode folder in the optional episode_path input. If it is blank, the workflow chooses the newest episode with a READY marker or incoming images.
- **One episode per push:** a push-triggered run must identify exactly one episode. Upload or commit files for different episodes in separate commits.
- **Validation:** checks the episode package and requires the expected 48 scenes and 48 supported input images. Use either one ZIP or 48 individual image files, not a mixture.
- **Rendering:** uses the episode narration, Edge TTS and FFmpeg to produce the final 16:9 video. It also creates word-aligned karaoke captions using faster-whisper.
- **Artifact:** uploads the final MP4 as a topic-named GitHub Actions artifact. The artifact retention period is **2 days**; download it promptly from the workflow run's Artifacts section.
- **Telegram delivery:** attempts to send the finished MP4 to the configured Telegram chat. The send step is allowed to fail without stopping the workflow.
- **Cleanup after successful delivery:** only if Telegram reports a successful send, the workflow deletes every uploaded file from images/incoming/ (including the retained source-upload.zip and scene images) and removes READY.txt, while preserving .gitkeep, episode metadata, script, prompts and rendered output. It commits those deletions to main. The original ZIP therefore remains available during rendering and delivery, then is removed together with the extracted images.
- **If Telegram delivery fails:** cleanup is skipped and the uploaded files remain in the repository so you can retry. The MP4 artifact was uploaded before the Telegram step, so it can still be downloaded even if Telegram delivery fails.

Wait for the cleanup commit to reach main before uploading the same ZIP filename again to the same episode. A new upload should be a new commit after the prior cleanup has completed.

### 5. AI Video Experiment (separate legacy generator)

File: [.github/workflows/ai-video-test.yml](.github/workflows/ai-video-test.yml)

- **Automatic schedule:** every day at 05:30 UTC (11:00 India Standard Time).
- **Manual start:** Actions → AI Video Experiment → Run workflow.
- **Entry point:** main_ai.py.
- **What it does:** generates a story using the root-level generator, creates AI scene artwork through the Cloudflare Workers AI integration, generates narration with Edge TTS, and renders an MP4 with FFmpeg.
- **Telegram and artifact:** sends the experiment video to Telegram and uploads the video plus story JSON as an Actions artifact retained for 7 days.
- **Topic history:** publishes `used_story_topics.json` from an isolated worktree with fetch/retry and duplicate-safe merging. This bookkeeping step is non-blocking so a push race cannot skip subtitle generation or delivery; check its warning if history sync fails.
- **Keep it separate:** this is not the 48-image Science Channel episode pipeline. It uses the root config.json, root scripts/ folder and root topic history. It does not use science-channel/settings.json or Science Channel episode folders.

---

## Science Channel: episode lifecycle

The episode package is created first; images are a separate human-reviewed stage; rendering happens only after the images are committed.

Example folder:

    science-channel/
      daily-episodes/
        2026-11-01/
          episode-001-example-topic/
            episode.json
            script.md
            scenes.json
            image-prompts.md
            images/
              incoming/
                .gitkeep
            output/

| File/folder | What it contains |
|---|---|
| episode.json | Episode title, metadata and expected scene count |
| script.md | Narration divided into Scene 01 through Scene 48 |
| scenes.json | Structured scene descriptions and narration |
| image-prompts.md | One image-generation prompt for each scene |
| images/incoming/ | ZIP or 48 individual scene images waiting to render |
| READY.txt | Marker indicating that the image set is ready for rendering |
| output/ | Rendered MP4 and temporary/supporting render output |

### Recommended image workflow

1. Run the Daily Gemini Planner or wait for its scheduled run.
2. Review episode.json, script.md, scenes.json and image-prompts.md. Keep all 48 scenes in order.
3. Generate one landscape 16:9 image for each scene prompt.
4. Upload the 48 images using Telegram Image Receiver, Telegram ZIP Import, or directly into the episode's images/incoming/ folder.
5. For direct repository uploads, include READY.txt in the commit or manually start the renderer with the exact episode_path.
6. Download the topic-named artifact from the renderer run within 2 days.

Detailed image preparation, ZIP sizing, file editing, scene validation and troubleshooting instructions are in the [Science Channel operating guide](science-channel/README.md).

## Repository layout

- **Root generator:** `main_ai.py` powers the scheduled AI Video Experiment; `free_science_video.py` remains a separate local Blender-stills experiment.
- **Root configuration:** config.json controls the legacy generator's scene count, output dimensions, frame rate, Gemini model and voice.
- **Root scripts/:** story generation, image generation, voice generation, visual rendering and FFmpeg assembly for the root generator.
- **Science Channel:** science-channel/settings.json, topics.txt, history/, scripts/ and daily-episodes/ contain the episode-based pipeline.
- **GitHub Actions:** .github/workflows/ contains the five workflows described above.
- **ai-video-experiment/README.md:** additional notes for the separate Cloudflare AI Video Experiment.

## Cloudflare Worker deployment

The Worker source used by the Telegram control centre is [`cloudflare-worker.js`](cloudflare-worker.js). Deploy this source to the existing Worker after changes, keeping its current environment variables and secrets. The Worker handles normal Telegram commands and forwards image/ZIP uploads plus `/episode` selection messages to the Telegram Image Receiver workflow.

After deploying the updated source, open `https://frosty-disk-7c9e.pallipattumanoj.workers.dev/setup` once to register the Telegram webhook. Do not start a second Telegram polling process or re-enable `getUpdates`/ `deleteWebhook` in GitHub Actions while this webhook is active. The Worker's `GITHUB_TOKEN` needs repository Contents read/write permission so it can save each update under `.github/telegram-inbox/`. The resulting push starts the receiver workflow.

## GitHub repository configuration

Open **Settings → Secrets and variables → Actions** to configure the following repository secrets:

| Secret / variable | Required for | Purpose |
|---|---|---|
| GEMINI_API_KEY | Daily Gemini Planner; AI Video Experiment; local Gemini-based generation | Gemini text generation for scripts, topics and prompts |
| TELEGRAM_BOT_TOKEN | Telegram prompt/image/video workflows | Authenticates the Telegram bot |
| TELEGRAM_CHAT_ID | Telegram prompt/image/video workflows | Restricts delivery and accepted messages to the intended chat |
| GH_PAT | Telegram ZIP Import | Token with repository contents write access, used to push imported images to main |
| CF_ACCOUNT_ID | AI Video Experiment | Cloudflare account identifier |
| CF_API_TOKEN | AI Video Experiment | Cloudflare Workers AI API access |
| SCIENCE_GEMINI_MODEL (repository variable, optional) | Daily Gemini Planner | Overrides the model configured in science-channel/settings.json |

Secrets are sensitive: add them in GitHub repository settings, never in README files, source code, workflow inputs or commits. The root AI experiment also needs the Cloudflare secrets; the Science Channel planner does not.

## Local experiment

`free_science_video.py` is a separate local Blender-stills experiment. The scheduled AI Video Experiment runs `main_ai.py` through GitHub Actions.

## Alternative free LLM providers (Gemini backup)

If Gemini API access or the configured model becomes unavailable, consult the community-maintained [Awesome Free LLM APIs catalogue](https://github.com/mnfst/awesome-free-llm-apis/blob/main/README.md) for current providers and models, including options such as Groq, Cloudflare Workers AI, OpenRouter, Mistral and Cohere.

Provider availability, free quotas, rate limits, model IDs and terms change. Check the provider's official documentation before switching. A model listed in the catalogue is **not necessarily a drop-in Gemini replacement**: the project may need a different endpoint, authentication method, request schema or client implementation, followed by testing. Add any required API key as a GitHub Actions secret.

## Operational notes

- Science Channel episodes, uploads, receiver state and cleanup commits are intended for **main only**. The planner and Telegram receiver share a concurrency group to serialize main-branch writes.
- Do not upload a ZIP to the repository root or beside an MP4. Use the exact episode images/incoming/ folder for direct renderer uploads, or science-channel/telegram-uploads/ for the manual Telegram ZIP Import route.
- Telegram delivery requires a reachable bot and valid token/chat ID. A failed send does not necessarily mean rendering failed; check the artifact section of the Actions run.
- GitHub Actions artifacts expire automatically according to the retention period stated for each workflow: 2 days for Science Channel renders and 7 days for the AI Video Experiment.
- Workflow schedules use UTC. India Standard Time is UTC+05:30.


## How to customize the project (what to edit)

Make changes on **main** unless you are deliberately working on a separate experiment. In GitHub, open the file, click the pencil icon, edit it, then commit the change to main. For larger edits, use a local clone and a pull request. Never put API keys or bot tokens in these files.

| Change you want | File to edit | Notes |
|---|---|---|
| Science Channel voice, language, resolution, FPS, Gemini model, target length | `science-channel/settings.json` | The renderer reads voice, speech rate, width, height and FPS. The planner reads the Gemini model and episode settings. |
| Science topic seed ideas | `science-channel/topics.txt` | Add one idea per line. Gemini can also invent topics within its selected category. |
| Science episode writing style, topic categories, hook and prompt rules | `science-channel/scripts/gemini_planner.py` | Edit the topic-pillar examples and prompt text. Keep duplicate-history checks intact. |
| A specific episode's title, narration, scene order or image prompts | That episode's `episode.json`, `script.md`, `scenes.json`, `image-prompts.md` | Keep all 48 scene numbers aligned. Update narration, scene data and image prompt together. |
| Science Channel karaoke caption appearance | `science-channel/scripts/karaoke_subtitles.py` | Controls font, size, position, outline, phrase length and highlight color. |
| Science Channel Telegram receiver behavior | `science-channel/scripts/telegram_image_receiver.py` | Telegram file types, image-size limits, episode selection and bot commands. |
| ZIP import validation and size limits | `science-channel/scripts/import_telegram_zip.py` | Staging folder, file extensions, ZIP/image size limits and safe archive checks. |
| When a workflow runs, permissions, timeout or artifact retention | Matching file in `.github/workflows/` | Cron is UTC. Keep branch and path filters correct. |
| Legacy AI experiment length, voice, dimensions, FPS, model preference | `config.json` | This config is not used by the Science Channel episode renderer. |
| Legacy AI experiment topic ideas | Root `topics.txt` | Separate from `science-channel/topics.txt`. |
| Legacy AI experiment illustration style | `scripts/make_art.py` | Edit the `STYLE` string. The active Cloudflare model URL is also in this file. |
| Legacy AI experiment narration and scene-generation instructions | `scripts/generate_story.py` | Edit the prompt and model fallback list. |
| AI Video Experiment image providers and fallback order | `scripts/make_art.py` | Cloudflare primary, AI Horde backup and OVHcloud final fallback. |

**Important:** Science Channel is a fixed 48-scene pipeline. Do not change `scene_count` or `required_uploaded_images` from 48 in settings alone. The planner, Telegram receiver, ZIP importer, render validation, READY logic and image prompts also assume 48. Changing the count requires a coordinated code/workflow update and testing.

### Safe change examples

**Change Science Channel narration voice:** edit `science-channel/settings.json`, change `voice` to a supported Microsoft Edge TTS voice name, and optionally adjust `speech_rate` (for example `+5%` or `-5%`). The renderer uses these settings when it generates the narration. A voice change affects future renders, not already-rendered MP4 files.

**Change the Science Channel Gemini model:** change `gemini_model` in `science-channel/settings.json`, or set the optional Actions repository variable `SCIENCE_GEMINI_MODEL` under Settings → Secrets and variables → Actions → Variables. The variable takes precedence for the planner workflow. Check Google's current model availability before changing it.

**Change the legacy AI experiment voice or video dimensions:** edit `config.json`. The current legacy experiment configuration is 47 scenes, 8 target minutes, 1280×720, 24 FPS, and a 7-day artifact retention value. This does not alter Science Channel's 48-scene, 1920×1080, 30 FPS settings.

**Change the daily schedule:** edit the relevant workflow's `on.schedule.cron` value. GitHub cron uses UTC, not local time. For example, `15 1 * * *` means 01:15 UTC every day (06:45 IST). The Telegram receiver is webhook-triggered through the Cloudflare Worker; do not add a getUpdates polling schedule while the webhook is active.

### More detailed customization instructions

The [Science Channel operating guide](science-channel/README.md#customize-the-science-channel) explains every Science Channel setting, prompt, upload rule and render option. The [AI Video Experiment guide](ai-video-experiment/README.md) explains the separate root-level generator and how to customize its art, voice, topics and model.



---

# ☁️ Cloudflare & 📲 Telegram — integration manuals

The two integrations are used differently by the two video pipelines. Read the correct guide before changing credentials, providers, upload limits or workflow behavior.

## ☁️ Cloudflare Workers and Workers AI

Cloudflare **Workers AI** is currently used by the **root AI Video Experiment only**. It generates scene illustrations through the FLUX-2-KLEIN-4B model. The Science Channel episode pipeline does not currently call Cloudflare for image generation.

**Important architecture note:** the repository currently calls the Workers AI REST API directly from `scripts/make_art.py`. It does **not** currently deploy or run a separate Cloudflare Worker application. A deployed Worker is optional; it can be added as an API gateway/proxy if you want your own endpoint, authentication, validation, rate limiting or centralized configuration.

- Current direct API secrets: `CF_ACCOUNT_ID` and `CF_API_TOKEN`.
- Active implementation: `scripts/make_art.py`.
- Current model endpoint: `@cf/black-forest-labs/flux-2-klein-4b`.
- Current image request: Cloudflare FLUX.2 Klein at 1024 × 576 with bearer-token authentication; Cloudflare requests use bounded retries.
- Provider fallback: Cloudflare → anonymous AI Horde → anonymous OVHcloud SDXL. Images are saved scene-by-scene; if all providers fail for a scene, generation stops. No stickman fallback or unrelated image reuse is used.

The detailed manual explains the **actual implementation in this repository**: how `scripts/make_art.py` builds and sends Workers AI requests, how the GitHub workflow supplies credentials, and exactly where to change the model, prompt, dimensions, timeout, pacing and fallback. Start with [How this repository implemented Cloudflare and how to modify it](ai-video-experiment/README.md#-how-this-repository-implemented-cloudflare--exact-code-path-and-modification-map). It also documents the current Workers AI API setup and, separately, optional Cloudflare Worker deployment if you later want a custom gateway.

## 📲 Telegram

Telegram has four roles in the Science Channel and one in the legacy AI experiment:

1. Sends the Science Channel's `image-prompts.md` document after the planner commits an episode.
2. Receives 48 individual images or one ZIP using the Telegram Image Receiver.
3. Can import a ZIP staged in `science-channel/telegram-uploads/` using the manual Telegram ZIP Import workflow.
4. Receives the final Science Channel MP4 after rendering.
5. Receives the separate AI Video Experiment MP4.

Shared Science Channel/legacy secret names:
- `TELEGRAM_BOT_TOKEN` — token created through Telegram's official @BotFather.
- `TELEGRAM_CHAT_ID` — numeric private-chat or group ID used as the destination and incoming-chat allowlist.
- `GH_PAT` — additional GitHub token required only by the staged ZIP import workflow so it can push extracted images.

The Telegram Image Receiver is triggered by Cloudflare Worker webhook events; it does not poll Telegram. It accepts JPG/JPEG, PNG and WebP, supports 48 individual images or one 48-image ZIP, and writes a READY marker when all 48 scene slots exist. The staged ZIP importer has separate validation and size limits. The renderer sends the MP4 and cleans source images only after successful Telegram delivery.

Read the detailed manuals:
- [Science Channel — how the Telegram bot is implemented, Python receiver functions, webhook-triggered receiver workflow and how to modify it](science-channel/README.md#1a-how-the-existing-bot-is-implemented-code-level-map)
- [Science Channel — complete Telegram setup, commands, image uploads, ZIP import, video delivery and cleanup](science-channel/README.md#-telegram-operations--detailed-science-channel-manual)
- [AI Video Experiment — Telegram bot implementation, outgoing senders and exact modification map](ai-video-experiment/README.md#-how-the-telegram-bot-is-actually-implemented-in-this-repository)
- [AI Video Experiment — Telegram bot setup, secrets, Bot API behavior, delivery order and troubleshooting](ai-video-experiment/README.md#-telegram--complete-bot-setup-upload-delivery-and-modification-guide)

**Security:** Never commit Cloudflare tokens, Telegram bot tokens, Gemini keys or GitHub PATs. Store them in repository Settings → Secrets and variables → Actions → Secrets. Keep the Science Channel workflows on `main`.

## 🛠️ Troubleshooting: Telegram bot stops replying (Cloudflare Worker)

Use this checklist if the Telegram bot ignores `/start`, `/menu`, `/help`, upload commands, or stops forwarding image uploads. This documents the recovery procedure that fixed the November 2026 outage.

**Architecture:** Telegram sends updates to the Cloudflare Worker webhook. The Worker handles control-centre commands and forwards image/ZIP uploads to the GitHub Actions Telegram Image Receiver. GitHub Actions does not poll Telegram. Do not add a second polling process or call Telegram `getUpdates` while the webhook is active.

### 1. Check the live Worker

Open these URLs in a browser:

- Health check: [Worker /health](https://frosty-disk-7c9e.pallipattumanoj.workers.dev/health)
- Webhook setup: [Worker /setup](https://frosty-disk-7c9e.pallipattumanoj.workers.dev/setup)

The health endpoint should return a successful response. The setup endpoint registers the Telegram webhook. A successful setup response looks like:

```json
{
  "webhook_url": "https://frosty-disk-7c9e.pallipattumanoj.workers.dev/",
  "telegram_response": {
    "ok": true,
    "result": true,
    "description": "Webhook was set"
  }
}
```

Only run/open `/setup` when you intend to (re)register the webhook. It changes the bot's webhook configuration. If Telegram reports an error, check the Worker secrets and URL before trying again.

### 2. Confirm the complete Worker source is deployed

A previous failure was caused by an incomplete `cloudflare-worker.js` in the repository: the message handler called the command router, but the deployed source did not contain the router and several command functions. Incoming Telegram messages therefore could not be handled correctly.

1. Open [the canonical cloudflare-worker.js on main](https://github.com/manojkumar166-png/stickman-lab/blob/main/cloudflare-worker.js).
2. Confirm it is the complete current file. Do not restore an older or shortened copy.
3. In [Cloudflare Dashboard](https://dash.cloudflare.com/), open **Workers & Pages** and select the existing Worker **frosty-disk-7c9e**.
4. Open **Edit code** and replace the Worker editor contents with the complete current `cloudflare-worker.js` from the repository.
5. Save and **Deploy**.
6. Recheck `/health`, then open `/setup` once to register the webhook again.
7. Send `/start` to the bot in Telegram.

**Important:** a commit or push to GitHub does not by itself prove that the existing Cloudflare Worker has been deployed. If this Worker is not connected to an automatic deployment pipeline, deploy it manually as described above.

### 3. Verify Cloudflare Worker environment variables and secrets

In Cloudflare Dashboard → Workers & Pages → **frosty-disk-7c9e** → **Settings** → **Variables and Secrets**, check that the following are configured for the deployed environment:

| Name | What to check |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Valid bot token from @BotFather. Keep it secret. |
| `TELEGRAM_ALLOWED_USER_ID` | Your numeric Telegram user ID, as a string or number. It must match the account sending commands; an @username is not a substitute. |
| `TELEGRAM_WEBHOOK_SECRET` | The webhook secret used by the Worker when registering the webhook. It must be present and consistent with the webhook registration. |
| `GITHUB_TOKEN` | GitHub token used by the Worker for repository operations/inbox forwarding. It needs the repository permissions required by the Worker, including contents write access for inbox commits. |
| `PUBLIC_WORKER_URL` | Optional public base URL. If set, it must be the deployed Worker URL; otherwise the Worker may use its built-in default URL. |

Do not paste tokens, secrets, or full credential values into Telegram, GitHub issues, screenshots, or chat messages. If a credential may have been exposed, rotate it at its issuing service and update the Cloudflare secret.

**Silent no-reply check:** the Worker authorizes commands by comparing the sender's numeric Telegram user ID with `TELEGRAM_ALLOWED_USER_ID`. If that variable is blank or incorrect, the message handler intentionally ignores the message. Verify the exact numeric ID before changing code.

**Webhook authentication check:** if the Worker rejects webhook POST requests with HTTP 401, verify that `TELEGRAM_WEBHOOK_SECRET` is configured and matches the secret used when `/setup` registered the webhook. After correcting it, run `/setup` once again.

### 4. Check Cloudflare logs and classify the symptom

In Cloudflare Dashboard → Workers & Pages → **frosty-disk-7c9e** → **Logs** (or Observability), inspect requests while sending a fresh `/start` message.

| Symptom | Likely check |
|---|---|
| Telegram message receives no reply and there is no useful Worker activity | Confirm the webhook URL is set, the Worker is deployed, and the bot token is correct. |
| Webhook POST returns **401** | Check `TELEGRAM_WEBHOOK_SECRET` and re-register with `/setup`. |
| Worker receives the update but no command reply is sent | Check `TELEGRAM_ALLOWED_USER_ID` against the sender's numeric Telegram user ID; inspect Worker exceptions and Telegram API errors. |
| Error mentions `handleCommand is not defined` or another missing function | The deployed Worker source is incomplete or outdated. Redeploy the complete repository `cloudflare-worker.js`. |
| Commands reply, but image/ZIP uploads do not reach GitHub Actions | Check `GITHUB_TOKEN`, repository write permissions, GitHub API errors, and the Telegram Image Receiver workflow run/inbox. |
| Webhook setup fails | Check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_WORKER_URL`, and the response body returned by Telegram. |

### 5. Verify end-to-end recovery

After correcting the issue:

1. Confirm `/health` responds successfully.
2. Confirm `/setup` returns Telegram `ok: true` and `description: "Webhook was set"` (only after intentionally registering the webhook).
3. Send `/start` in the authorized Telegram account and confirm the bot replies.
4. Test the relevant command, such as `/menu` or `/status`.
5. If testing image intake, send a test image and verify that the GitHub **Telegram Image Receiver** workflow starts and records the upload. Continue using the existing 48-image process.

### 6. Protect the working video pipeline

When fixing Telegram connectivity, change only the Cloudflare Worker deployment or the specific incorrect Worker secret. Do not delete or rewrite Science Channel episode folders, the 48-image upload receiver, ZIP importer, renderer, READY marker, or delivery/cleanup logic as a shortcut. Keep the existing workflows on `main`. If a code change is required, start from the complete current `cloudflare-worker.js`, review the diff, and test commands plus upload forwarding before changing other pipeline components.


## AI Story & Science Video Creator — one-click 48-scene workflow

This is a separate generator from the Science Channel episode pipeline and the legacy AI Video Experiment.

**Run it:** Actions → **AI Story & Science Video Creator** → **Run workflow** → select `main` → **Run workflow**. There are no input fields. Each run asks Gemini to invent a fresh topic from the root `topics.txt` inspiration library and generates **48 scene images**, narration and a final MP4. The default voice is `en-US-AndrewMultilingualNeural`.

- Workflow: [`.github/workflows/ai-story-science-video.yml`](.github/workflows/ai-story-science-video.yml)
- Complete guide: [`ai-story-science-video/README.md`](ai-story-science-video/README.md)
- Generator code: [`scripts/ai_story_video.py`](scripts/ai_story_video.py)
- Topic inspiration: [`topics.txt`](topics.txt)
- Used-topic history: [`used_story_topics.json`](used_story_topics.json)

### Change the defaults

| Want to change | Edit this | Current behaviour |
|---|---|---|
| Always generate 48 scenes | `.github/workflows/ai-story-science-video.yml` | The run command contains `--scenes 48`. |
| Change scene count | Same workflow file, find `--scenes 48` | Change 48 to the desired number (the script accepts 4–48). |
| Change narration voice | Same workflow file, find `--voice "en-US-AndrewMultilingualNeural"` | Replace with a supported Edge TTS voice ID. |
| Give Gemini different topic inspiration | Root `topics.txt` | Add or remove one idea per line; Gemini uses it as inspiration, not a fixed queue. |
| Change Gemini model/fallback | GitHub repository Settings → Secrets and variables → Actions → Variables | Set `GEMINI_MODEL` and optionally `GEMINI_FALLBACK_MODELS`. |
| Improve image style and framing | `scripts/ai_story_video.py`, function `generation_prompt()` | Cinematic 3D CGI, detailed materials/lighting and 16:9 center-safe composition. |
| Change image providers/order, rate limits or retries | Same Python file, functions `ovh()`, `ai_horde()`, `vexa()`, `pollinations()`, `generate_all()` | Anonymous free-provider fallback chain; no paid API key is configured. |
| Change subtitles | `science-channel/scripts/karaoke_subtitles.py` | Reuses the Science Channel word-highlight subtitle generator. |
| Change video encoding | Same Python file, function `render()` | FFmpeg segment and final-video encoding settings. |
| Change final artifact/Telegram delivery | `.github/workflows/ai-story-science-video.yml` | Only the final topic-named MP4 is uploaded/sent; artifact retained 7 days. |

**Important:** this workflow is deliberately configured for one-click 48-scene runs. Editing the scene count or voice requires a commit to the workflow file; you do not enter those values on the Actions screen. Free image providers have rate limits and queues, so 48 images can take a long time and are not guaranteed to complete on every run.

## Documentation map

Every active workflow has a dedicated guide. Start with [the workflow index](.github/workflows/README.md), which links to all eight workflow guides.

- [Science Channel operating guide](science-channel/README.md) — shared episode format, planner, image preparation, Telegram operations and renderer behavior.
- [AI Story & Science Video Creator](ai-story-science-video/README.md) — standalone free-provider 48-scene generator.
- [AI Video Experiment](ai-video-experiment/README.md) — separate Gemini + Cloudflare Workers AI experiment.
- [Individual workflow guides](.github/workflows/guides/) — triggers, execution, configuration, outputs, troubleshooting and rollback for the Science Channel planner, Telegram receiver, ZIP importer, renderer and workflow validator.

The root README is the repository map and operational handbook. The linked guides provide implementation-level details for each component.


---

# Complete operations handbook

This section expands the quick-start map above into a practical reference for operating the repository, understanding how the automation connects, making safe changes and recovering from failures. The workflow YAML and Python scripts remain the source of truth; if a setting in this document ever differs from the current code, inspect the linked implementation before making a production change.

## 1. Architecture at a glance

There are three distinct video-generation paths. They share some infrastructure (GitHub Actions, Telegram delivery and FFmpeg) but do not share all configuration or source files.

| Pipeline | Planning/story source | Artwork source | Rendering | Main configuration |
|---|---|---|---|---|
| Science Channel | Daily Gemini Planner creates an episode package | Human-prepared images uploaded by Telegram, ZIP importer or repository commit | Science Channel renderer | `science-channel/settings.json`, episode package |
| AI Story & Science Video Creator | Gemini creates a story and scene plan during the run | Anonymous/free image-provider fallback chain in the generator | Dedicated Python/FFmpeg workflow; karaoke helper reused | Root `topics.txt`, workflow command, Actions variables |
| AI Video Experiment | Root AI generator creates the story | Cloudflare Workers AI integration in the root generator | Root generator and FFmpeg | Root `config.json`, Cloudflare/Gemini secrets |

Do not assume that a setting in one pipeline affects another. In particular:

- `science-channel/settings.json` belongs to the episode-based Science Channel pipeline.
- Root `config.json` belongs to the legacy/root generator used by AI Video Experiment and local experiments.
- Root `topics.txt` and `used_story_topics.json` are separate from `science-channel/topics.txt` and `science-channel/history/generated-topics.json`.
- AI Story & Science Video Creator is a separate standalone generator; it has its own used-topic history file, `used_story_topics.json`.

## 2. Workflow inventory and operational matrix

All eight active workflows are listed in [`.github/workflows/README.md`](.github/workflows/README.md). This table summarizes their operational role.

| Workflow | Trigger | Main output or side effect | Main branch behavior |
|---|---|---|---|
| Science Channel — Daily Gemini Planner | Daily schedule and manual dispatch | Creates one episode package and reserves its topic in history; optionally sends prompts to Telegram | Commits episode and history to `main` |
| Telegram Image Receiver | Worker-forwarded inbox push and manual maintenance dispatch | Saves received scene images and receiver state; may create `READY.txt` | Commits intake changes to `main` |
| Telegram ZIP Import | Manual dispatch with episode and ZIP paths | Extracts staged ZIP, creates READY marker and removes staged ZIP | Commits import and staging deletion to `main` |
| Free Science Visuals — Render Ready Episode | Incoming-image/READY push or manual dispatch | Renders final MP4, uploads artifact, attempts Telegram delivery; cleans source uploads only after successful send | Cleanup commit to `main` |
| AI Video Experiment | Daily schedule and manual dispatch | Generates the experiment video, updates topic history, sends the final video | Topic history is committed to `main` |
| AI Story & Science Video Creator | Manual dispatch, no inputs | Generates standalone 48-scene story video and sends final MP4 | Updates its used-topic history on `main` |
| Validate Workflows | Workflow-file push/PR and manual dispatch | Runs actionlint checks; no media output | Read-only validation |

### Schedule reference

The scheduled workflow times are expressed in UTC. India Standard Time is UTC+05:30.

| Workflow | Cron in YAML | India Standard Time |
|---|---:|---:|
| Science Channel Daily Planner | `15 1 * * *` | 06:45 daily |
| AI Video Experiment | `30 5 * * *` | 11:00 daily |

GitHub may delay scheduled starts during periods of load. A cron time is the earliest scheduled start target, not a guarantee that a job begins at that exact minute. The other workflows are event-driven or manually dispatched.

## 3. First-time setup checklist

Complete these steps before relying on the automated pipeline.

### GitHub repository

1. Open the repository's **Settings → Secrets and variables → Actions**.
2. Add only the secrets required by the workflows you intend to run (see the credential table below).
3. Add optional repository variables for model overrides if you want to override defaults.
4. Confirm GitHub Actions is enabled for the repository and that the workflows are visible under the Actions tab.
5. Confirm the automation tokens have the minimum permissions required by their specific workflow.
6. Keep Science Channel planner, receiver, importer, renderer and cleanup operations on `main`.

### Telegram

1. Create or select the bot using Telegram's official **@BotFather**.
2. Configure the correct numeric destination/source chat ID.
3. Add the token and chat ID as GitHub Actions secrets.
4. If using the Cloudflare Worker control centre, configure its Cloudflare-side variables/secrets separately.
5. Deploy the complete `cloudflare-worker.js` source to the existing Worker and register the webhook through its documented setup endpoint.
6. Send a simple command and verify the Worker replies before attempting a large image upload.

Do not run a separate Telegram `getUpdates` polling process while the Worker webhook is active. The webhook is the intake owner and forwards updates to GitHub.

### Cloudflare Worker

The Telegram control-centre Worker is a separate deployed service. Updating `cloudflare-worker.js` in GitHub does not necessarily deploy it to Cloudflare. After changing the source, deploy it through the Cloudflare dashboard or the repository's configured deployment mechanism, then test its health and webhook setup endpoints. See the [Cloudflare Worker recovery guide above](#-troubleshooting-telegram-bot-stops-replying-cloudflare-worker).

## 4. Secrets and variables reference

Secrets belong in **Settings → Secrets and variables → Actions → Secrets**. Variables belong in the Variables tab. Never commit their values.

| Name | Kind | Used by | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | Secret | Daily Gemini Planner, AI Video Experiment, AI Story workflow | Gemini authentication |
| `GEMINI_MODEL` | Variable | AI Story & Science Video Creator | Optional model override |
| `GEMINI_FALLBACK_MODELS` | Variable | AI Story & Science Video Creator | Optional comma-separated model fallback configuration as interpreted by the script |
| `SCIENCE_GEMINI_MODEL` | Variable | Science Channel Daily Planner | Optional planner model override |
| `TELEGRAM_BOT_TOKEN` | Secret | Telegram prompt, image, ZIP-import alerts and video delivery | Bot API credential |
| `TELEGRAM_CHAT_ID` | Secret | Telegram prompt, image, ZIP-import alerts and video delivery | Numeric chat destination/allowlist |
| `GH_PAT` | Secret | Telegram ZIP Import | Repository contents write access for the import commit |
| `CF_ACCOUNT_ID` | Secret | AI Video Experiment | Cloudflare account identifier |
| `CF_API_TOKEN` | Secret | AI Video Experiment | Workers AI API authorization |

The Telegram Image Receiver workflow and the Cloudflare Worker have distinct configuration surfaces. The GitHub workflow secrets do not automatically configure the deployed Worker. The Worker uses its own Cloudflare environment variables/secrets, including the bot token, allowed Telegram user ID, webhook secret, GitHub token and public Worker URL as documented in the Telegram troubleshooting section.

If a secret is rotated, update it in every service that uses it. A successful GitHub workflow configuration does not prove the Cloudflare Worker has received the new value.

## 5. Science Channel episode lifecycle — detailed handoff

The Science Channel pipeline deliberately separates planning from artwork creation and rendering.

```text
Daily Gemini Planner
        |
        v
Episode package committed to main
        |
        v
Review script.md + scenes.json + image-prompts.md
        |
        v
Create 48 scene images
        |
        +---- Telegram Image Receiver
        |
        +---- Telegram ZIP Import
        |
        +---- Direct repository upload
        |
        v
48 incoming scene images + READY.txt
        |
        v
Free Science Visuals renderer
        |
        +---- Validate episode and images
        +---- Generate narration / align word timestamps
        +---- Render MP4 with karaoke captions
        +---- Upload final MP4 artifact
        +---- Attempt Telegram delivery
        |
        v
If Telegram delivery succeeds:
remove incoming uploads + READY marker and commit cleanup
```

### Episode package contract

A typical episode folder is:

```text
science-channel/daily-episodes/YYYY-MM-DD/episode-NNN-topic/
├── episode.json
├── script.md
├── scenes.json
├── image-prompts.md
├── READY.txt                  # created when image set is ready
├── images/
│   └── incoming/
│       ├── .gitkeep
│       └── scene image files or one ZIP
└── output/
    ├── final topic-named MP4
    └── work/                  # temporary render assets
```

The exact output files can vary as the renderer progresses. The required input files and validation rules are defined in `science-channel/scripts/render_episode.py`.

### Scene numbering rules

The current Science Channel pipeline is designed for 48 scenes. Keep these aligned:

- Episode metadata's scene count.
- The ordered records in `scenes.json`.
- The `## Scene N` sections in `script.md`.
- The image prompts and uploaded image count.
- Telegram receiver slot numbering and READY marker logic.
- ZIP importer validation.
- Renderer validation and settings defaults.

Changing only one of these is not a supported way to change episode length. Treat a scene-count change as a coordinated project change and test it with a non-production episode first.

### Upload route selection

Use exactly one route for a given episode's image set:

- **Direct Telegram uploads:** the Cloudflare Worker forwards Telegram updates to the receiver. Individual images are assigned to the next missing slot by arrival order; send them in the intended order.
- **Telegram ZIP upload:** send one ZIP to the bot if the receiver's ZIP validation requirements are met. Do not combine it with individual uploads already in the episode.
- **Repository ZIP staging:** put the ZIP in `science-channel/telegram-uploads/`, then manually run Telegram ZIP Import with the exact episode and ZIP paths.
- **Direct repository images:** commit the image files into that episode's `images/incoming/` folder. Include the READY marker or manually run the renderer with the exact episode path.

Do not mix a ZIP with individual image files in the same incoming directory. The importer and renderer intentionally validate the image set before rendering.

### Renderer cleanup is destructive

The renderer uploads the final MP4 artifact before attempting Telegram delivery. It removes incoming source files and `READY.txt` only when Telegram delivery reports success. If delivery fails, the source images/ZIP remain available for another attempt.

Before changing this behavior, consider whether the committed incoming files are the only retained copy of the source artwork. If cleanup already happened, reverting the cleanup commit restores the files to Git history; it does not recall a video already delivered to Telegram.

## 6. Customization guide — choose the correct file

| Desired change | File or setting | Scope |
|---|---|---|
| Science narration voice or speech rate | `science-channel/settings.json` | Science Channel renderer |
| Science output resolution/FPS | `science-channel/settings.json` | Science Channel renderer |
| Science Gemini model | `SCIENCE_GEMINI_MODEL` variable or Science settings | Science Channel planner |
| Science topic categories/style/history | `science-channel/topics.txt`, planner script and history | Science Channel planner |
| Edit one episode's script/title/scenes/prompts | Files inside that episode folder | One episode only |
| Science karaoke caption style | `science-channel/scripts/karaoke_subtitles.py` | Science Channel and workflows reusing helper |
| Science incoming Telegram behavior | `science-channel/scripts/telegram_image_receiver.py` | Telegram receiver |
| ZIP staging and validation | `science-channel/scripts/import_telegram_zip.py` | Manual ZIP importer |
| Science render and image validation | `science-channel/scripts/render_episode.py` | Science renderer |
| Science planner schedule | `science-channel-daily-planner.yml` | Daily trigger |
| Science renderer trigger/timeout/artifact/cleanup | `free-science-visuals.yml` | Render workflow |
| AI Story scene count/voice | `ai-story-science-video.yml` command line | Standalone AI Story workflow |
| AI Story image prompt/provider chain | `scripts/ai_story_video.py` | Standalone AI Story workflow |
| AI Story model selection | `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` variables | Standalone AI Story workflow |
| AI Video Experiment dimensions/voice/length | Root `config.json` | Legacy/root generator |
| AI Video Experiment story prompt | `scripts/generate_story.py` | Legacy/root generator |
| AI Video Experiment image model/style | `scripts/make_art.py` | Legacy/root generator |
| AI Video Experiment schedule | `ai-video-test.yml` | Scheduled experiment |
| Telegram Worker commands/webhook | `cloudflare-worker.js` plus Cloudflare Worker settings | Deployed Telegram control centre |
| Workflow syntax validation | `validate-workflows.yml` | Lint/validation only |

### Safe editing sequence

1. Identify which pipeline owns the behavior you want to change.
2. Read that workflow's guide from [the workflow index](.github/workflows/README.md).
3. Fetch the current YAML/script/config from `main`; do not base an edit on an old local copy.
4. Change the smallest number of files that implement the behavior.
5. Search the repository for the setting, path, filename or function name to find dependent code.
6. Inspect the complete diff and check for accidental changes to secrets, branches, concurrency groups, topic history or cleanup logic.
7. Run the workflow validator after YAML changes.
8. Run the affected workflow manually where safe and inspect the full log, artifact and Telegram result.
9. Verify any expected commit or cleanup on `main` before considering the change complete.

## 7. Testing and verification

A commit is not proof that a workflow completed successfully. Verify each layer separately.

| Change type | Minimum verification |
|---|---|
| Workflow YAML | Validate Workflows passes; inspect trigger, permissions, branch, inputs and expressions |
| Planner prompt/model | Run planner manually; inspect topic choice, generated package and topic history commit |
| Telegram receiver | Send a controlled test update; inspect Worker logs, inbox push, receiver run and saved image/state |
| ZIP importer | Use a test episode and ZIP; inspect validation, extracted scene filenames, READY marker and staged ZIP removal |
| Renderer | Use a test episode; inspect image validation, narration, captions, MP4 playback and artifact |
| Telegram delivery | Confirm the bot delivered the correct file to the correct chat |
| Cloudflare Worker | Deploy the source, test health, register webhook if required and test an authorized command |
| Cleanup | Confirm cleanup only ran after successful Telegram delivery and inspect the cleanup commit |

For local Python checks, use the repository's Python requirements and FFmpeg dependencies. Keep credentials in environment variables or a local untracked environment file; never commit them. Use a test episode rather than production source images when testing destructive cleanup or scene-count changes.

## 8. Troubleshooting decision tree

### Workflow did not start

- Check whether the event matches the YAML trigger (branch, changed path, schedule or manual dispatch).
- For a scheduled workflow, check that it is enabled and remember that GitHub can delay scheduled runs.
- For path-filtered workflows, verify the changed file path exactly matches the configured filter.
- For Telegram intake, check the Cloudflare Worker inbox commit; the receiver does not poll Telegram.

### Workflow started but failed early

- Read the first failing step, not only the final summary.
- Check dependency installation, Python version, FFmpeg availability and required input files.
- Confirm secrets exist under the exact names referenced by the YAML.
- Check whether a manual workflow input is a complete repository-relative path.

### Workflow completed but expected output is missing

- Confirm the final render/commit step actually ran and was not skipped by a condition.
- Check the artifact section of that exact Actions run and its retention window.
- Check Telegram action/API output separately; delivery can fail even when rendering succeeds.
- For Science Channel, verify the renderer's exact episode path and that one episode was selected.

### Git push or rebase failed

- Inspect branch protection and token permissions.
- Check whether another main-branch writer committed while the workflow was running.
- Retry using the workflow's normal retry mechanism or a fresh run after reviewing the repository state.
- Do not force-push or reset shared `main` to bypass a conflict.

### Telegram bot stopped responding

- Check the deployed Worker source, health endpoint, webhook registration and Cloudflare logs.
- Verify the allowed Telegram user ID and webhook secret.
- Confirm the Worker token and GitHub token have the required permissions.
- Do not enable polling while the webhook is active.

## 9. Rollback and recovery procedures

Prefer a normal revert commit over resetting shared history. Before reverting, inspect exactly which files the commit changed and whether it contains generated content or cleanup deletions.

### Revert a code or workflow change

```bash
git checkout main
git pull --ff-only
git revert <change-commit-sha>
git push origin main
```

After the revert, run Validate Workflows and manually test the affected workflow if the change affects runtime behavior.

### Restore Science Channel incoming images after successful cleanup

1. Find the cleanup commit created after Telegram delivery.
2. Inspect the commit to confirm it deletes only the expected incoming images and READY marker.
3. Revert that cleanup commit. This restores the incoming files and READY marker in Git.
4. Check the resulting push carefully: restoring READY/incoming files can trigger another render.
5. If you do not want another automatic render, coordinate the restoration with the workflow trigger rather than blindly pushing the files.

### Undo an incorrect ZIP import

1. Find the import commit.
2. Inspect the exact extracted images, READY marker and staged ZIP deletion.
3. Revert the import commit if restoring the staged ZIP and removing the imported files is the desired result.
4. Correct the archive or episode, then run the importer again.

### Undo a planner-generated episode

The planner commit includes both the new episode package and the no-repeat topic-history update. Review both before reverting. Reverting the commit restores the previous topic history and removes the new episode package. A Telegram prompt document already sent is not removed by Git rollback.

### Recover a failed render

If Telegram delivery failed, the renderer should leave incoming files and READY marker in place. Inspect the failure, fix the credential or upload issue and rerun the renderer manually with the exact episode path. If delivery succeeded and cleanup already ran, restore source files by reverting the cleanup commit before rerendering.

### Important limits of rollback

- A Git revert cannot recall a Telegram message or video already delivered.
- A Git revert cannot undo a Cloudflare deployment; redeploy the desired Worker source separately.
- A Git revert cannot restore an expired GitHub Actions artifact. Download important MP4s before retention expires.
- A token leak requires revoking/rotating the token at its issuing service and updating the corresponding secret; reverting source code is not enough.
- Do not use `git reset --hard` or force-push `main` as a routine rollback strategy.

## 10. Repository structure and ownership

| Path | Responsibility |
|---|---|
| `.github/workflows/` | Eight workflow definitions and the workflow index |
| `.github/workflows/guides/` | Detailed guides for the five operational Science Channel/validation workflows |
| `science-channel/settings.json` | Science Channel render/planning defaults |
| `science-channel/topics.txt` | Science topic inspiration |
| `science-channel/history/` | Science topic history |
| `science-channel/daily-episodes/` | Generated episode packages, incoming images and render output |
| `science-channel/scripts/gemini_planner.py` | Science episode planning |
| `science-channel/scripts/telegram_image_receiver.py` | Telegram image intake |
| `science-channel/scripts/import_telegram_zip.py` | Repository-staged ZIP import |
| `science-channel/scripts/render_episode.py` | Episode validation, narration and video rendering |
| `science-channel/scripts/karaoke_subtitles.py` | Word-aligned karaoke captions |
| `scripts/ai_story_video.py` | Standalone AI Story & Science Video Creator |
| `scripts/generate_story.py`, `scripts/make_art.py` | Root/legacy AI Video Experiment story and artwork |
| `main_ai.py` | Root AI Video Experiment entry point |
| `config.json` | Root/legacy generator configuration |
| `topics.txt`, `topic_history.json` | Root/legacy experiment topic inputs/history |
| `used_story_topics.json` | AI Story workflow used-topic history |
| `cloudflare-worker.js` | Telegram webhook/control-centre source deployed separately to Cloudflare |
| `ai-video-experiment/README.md` | AI Video Experiment detailed guide |
| `ai-story-science-video/README.md` | AI Story workflow detailed guide |

## 11. Production safety rules

- Keep API keys, bot tokens and PATs in secrets, never in source or documentation.
- Keep the Science Channel pipeline on `main`; its writers, receiver, importer, renderer and cleanup logic are designed around that branch.
- Preserve the shared concurrency group and fetch/rebase/push retry logic for workflows that write to `main`.
- Preserve topic-history files unless you intentionally want previously used topics to become eligible again.
- Do not change the 48-scene count in one file only.
- Do not remove the renderer's Telegram-success condition from source cleanup without intentionally changing the data-retention design.
- Do not mix the Telegram webhook with a second polling process.
- Keep an offline copy of final MP4s you need to retain; Actions artifacts expire.
- Use the workflow-specific guides for exact implementation details and always verify the current YAML/script before editing.

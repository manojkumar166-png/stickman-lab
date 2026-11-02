# AI Video Experiment — complete technical and customization guide

This guide covers the separate root-level **AI Video Experiment**. It is not the 48-scene Science Channel episode pipeline. The experiment uses Gemini for the story, then tries Cloudflare Workers AI, AI Horde and OVHcloud in order for scene images, followed by Edge TTS narration and FFmpeg rendering.

For the current episode-based pipeline, see [Science Channel operating guide](science-channel/README.md).

## 1. What the workflow does

Workflow file: `.github/workflows/ai-video-test.yml`

- Runs automatically every day at **05:30 UTC (11:00 India Standard Time)**.
- Can also be started manually from Actions → **AI Video Experiment** → Run workflow.
- Uses Python 3.11, installs FFmpeg and `requirements.txt`, then runs `python main_ai.py`.
- Generates a story using Gemini, creates scene illustrations using Cloudflare Workers AI with AI Horde and OVHcloud fallbacks, creates an MP3 narration with Edge TTS, and renders an MP4 with FFmpeg.
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
| `scripts/make_art.py` | Cloudflare primary provider, AI Horde and OVHcloud fallbacks, prompt/style, retries and image validation. |
| `scripts/make_voice.py` | Edge TTS voice and speech-rate handling. |
| `scripts/render_video.py` | FFmpeg video assembly, frame rate and encoding. |
| `.github/workflows/ai-video-test.yml` | Schedule, Actions permissions, secrets, Telegram delivery and artifact retention. |

The scheduled workflow runs `main_ai.py`. Obsolete standalone generator variants have been removed to keep the root pipeline focused.

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

### Change topic seeds and writing style

Add one topic per line to the root `topics.txt`. The generator randomly chooses an unused seed topic (based on exact topic-history matching). When the list is exhausted, Gemini is asked to invent a new topic using the existing examples as style guidance.

To change the audience, tone, hook, narration structure, scene descriptions or JSON schema, edit the prompt in `scripts/generate_story.py`. If you change the JSON keys, update the downstream scripts that read those keys too.

The root pipeline's history is `topic_history.json`; it is separate from `science-channel/history/generated-topics.json`. Do not delete history unless you intentionally want old subjects to become eligible again. The root pipeline's matching is not the same semantic duplicate review used by the Science Channel planner.

## 5. Image generation and provider fallback behavior

The active image generator is `scripts/make_art.py`. It processes each scene separately in this order:

1. **Cloudflare FLUX.2 Klein** — primary provider, with bounded retries for transient failures and rate limits.
2. **AI Horde** — anonymous backup if Cloudflare cannot generate the scene.
3. **OVHcloud SDXL** — final fallback if both earlier providers fail; requests are paced for the anonymous endpoint's rate limit.

Every returned image is validated and saved immediately as `output/<run-folder>/images/scene-NN.png`. This preserves already completed images if a later scene or video-rendering step fails.

There is no stickman-art fallback and no reuse of a different scene's image. If all three providers fail for any scene, image generation stops with an error that identifies the failed scene. The workflow should not silently produce a video with missing or unrelated visuals.

The providers are anonymous/free endpoints where available; their quotas, queue times, availability and terms can change. A fallback is an attempt, not a guarantee that a provider will be available. Inspect the Actions log for the provider name and error reported for each scene.

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
| All configured image providers fail | The run stops with a clear error; no stickman artwork is substituted. |
| FFmpeg not found | Confirm the workflow's FFmpeg install step completed; install FFmpeg locally for local runs. |
| Telegram step fails | Check bot token, chat ID, bot access to the chat and Telegram file-size/service limits. Since Telegram is before artifact upload, this may prevent the artifact step from running. |
| No artifact | Check whether the workflow reached the artifact upload step and whether the Telegram step succeeded. |
| Topic appears again | Check `topic_history.json` and whether the prior run reached the history commit step. |

## 11. Important separation from Science Channel

This is a separate 47-scene root generator. The Science Channel episode pipeline uses its own 48-scene setting, episode folders, topic history, Telegram image intake and render workflow. Do not change root `config.json`, root `topics.txt` or root `topic_history.json` expecting those changes to affect Science Channel episodes.

For the Science Channel's customization options, image upload methods, Telegram receiver, ZIP import, captions and rendering, read [science-channel/README.md](science-channel/README.md).


---

# 🧩 Cloudflare Workers — create, deploy, configure and modify a Worker

> **Important distinction:** this repository currently uses the **Workers AI REST API directly** from GitHub Actions. It does **not** currently contain a Cloudflare Worker application, a `wrangler.jsonc` file, or a Worker deployment workflow. You do not need to deploy a Worker to use the current image-generation setup described below. This section explains how to create and manage a real Cloudflare Worker if you want a stable API/proxy layer, custom authentication, request validation, rate limiting or centralized configuration in front of Workers AI.

## 1. What is the difference?

| Product | What it is | Used by the current repository? |
|---|---|---|
| Cloudflare Workers | A serverless application you write and deploy to a `*.workers.dev` URL or your own domain | **No** — no Worker is deployed by this repository today |
| Cloudflare Workers AI | Cloudflare-hosted AI models that your code can call using an API or a Worker AI binding | **Yes** — `scripts/make_art.py` calls the Workers AI REST API |
| Wrangler | Cloudflare's command-line tool for developing, configuring and deploying Workers | Not currently part of the root GitHub Actions workflow |

**Current architecture:** GitHub Actions → `main_ai.py` → `scripts/make_art.py` → Cloudflare Workers AI REST API → image bytes. The GitHub workflow holds `CF_ACCOUNT_ID` and `CF_API_TOKEN`.

**Optional Worker architecture:** GitHub Actions (or another client) → your deployed Worker URL → Workers AI → image response. In this design the Worker holds the Cloudflare AI credentials, and the client calls your Worker instead of the Cloudflare account API endpoint. You must change `scripts/make_art.py` and the GitHub secrets/configuration to use this architecture; simply creating a Worker does not make this repository use it.

## 2. Create a Worker in the Cloudflare dashboard

1. Sign in to the [Cloudflare dashboard](https://dash.cloudflare.com/).
2. Open **Workers & Pages**.
3. Choose **Create application** / **Create Worker** (the dashboard wording can change).
4. Choose the basic Worker starter/Hello World template.
5. Give it a clear name, for example `stickman-image-gateway`.
6. Create and deploy it. Cloudflare assigns a `https://<worker-name>.<your-subdomain>.workers.dev` address when the workers.dev route is enabled.
7. Open the URL to confirm the starter Worker responds.
8. Open the Worker in **Workers & Pages** whenever you need to edit its code, settings, routes or bindings.

This creates a real Worker, but it is initially just the starter application. It does not automatically connect to this repository or Workers AI.

## 3. Create and deploy a Worker with Wrangler (developer workflow)

Use this route if you want the Worker source code stored in Git and modified locally.

Requirements: Node.js/npm and a Cloudflare account.

```bash
npm create cloudflare@latest -- stickman-image-gateway
cd stickman-image-gateway
npx wrangler login
npx wrangler dev
```

- Follow the create-cloudflare prompts and choose a Worker starter.
- `wrangler login` opens Cloudflare authentication in your browser.
- `wrangler dev` runs the Worker locally; use the local URL printed by Wrangler to test it.
- Edit the generated entry file (commonly `src/index.js` or `src/index.ts`) to change request handling and responses.
- Deploy when ready:

```bash
npx wrangler deploy
```

Cloudflare recommends keeping the Wrangler configuration file as the source of truth. New projects can use `wrangler.jsonc`; older projects may use `wrangler.toml`. See the official [Wrangler commands](https://developers.cloudflare.com/workers/wrangler/commands/workers/) and [configuration guide](https://developers.cloudflare.com/workers/wrangler/configuration/).

## 4. Configure Worker variables and secrets

A Worker can have ordinary configuration values and encrypted secrets.

- **Variables** are for non-sensitive values such as a model name, default image width, environment label or feature flag.
- **Secrets** are for sensitive values such as API tokens and shared client keys. Never put tokens in source code or ordinary `vars`.

### Configure in the dashboard

1. Open **Workers & Pages** and select your Worker.
2. Open **Settings → Variables and Secrets**.
3. Select **Add**.
4. Choose the appropriate type (Text/JSON for non-sensitive configuration; **Secret** for credentials).
5. Enter the binding name and value.
6. Save and deploy the updated Worker version.

### Configure with Wrangler

Set a secret (Wrangler prompts for the value):

```bash
npx wrangler secret put CF_ACCOUNT_ID
npx wrangler secret put CF_API_TOKEN
```

If your Worker endpoint should require its own client authentication, create a separate secret such as `CLIENT_API_KEY`; do not reuse or expose the Cloudflare API token as the client key.

For local development, create a `.dev.vars` file beside the Wrangler config:

```dotenv
CF_ACCOUNT_ID="your-cloudflare-account-id"
CF_API_TOKEN="your-cloudflare-api-token"
CLIENT_API_KEY="your-private-client-key"
```

Add `.dev.vars` and `.dev.vars.*` to `.gitignore`. Never commit the real values. For production, use dashboard secrets or `wrangler secret put`, not a committed local file.

Official guides: [Worker environment variables](https://developers.cloudflare.com/workers/configuration/environment-variables/) and [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/).

## 5. Modify an existing Worker

You can modify a deployed Worker in either of two ways. Pick one source of truth and avoid making conflicting dashboard and local-code changes.

### Option A — edit in the dashboard

1. Go to **Workers & Pages → your Worker**.
2. Open **Edit code** (or the code editor shown for that Worker).
3. Change the JavaScript/TypeScript handler.
4. Save and deploy a new version.
5. Test the deployed URL with a harmless request.
6. Review the deployment/version history and logs if the behavior is not correct.

Use this for quick changes. If the Worker is managed by Wrangler from a Git repository, make the durable code change in that repository too; a later Wrangler deployment may overwrite dashboard-only edits.

### Option B — edit locally with Wrangler

1. Open the Worker project directory.
2. Modify the entry file under `src/` (or the entry path specified in `wrangler.jsonc` / `wrangler.toml`).
3. Change bindings, compatibility settings, routes, observability or environment configuration in the Wrangler config.
4. Test locally using `npx wrangler dev`.
5. Deploy with `npx wrangler deploy`.
6. For a staging environment, configure it in Wrangler and deploy with `npx wrangler deploy --env staging`; configure that environment's secrets separately.

Example configuration shape (illustrative; adapt the entry point and name to the generated project):

```jsonc
{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "stickman-image-gateway",
  "main": "src/index.js",
  "compatibility_date": "2026-11-01",
  "vars": {
    "IMAGE_MODEL": "@cf/black-forest-labs/flux-2-klein-4b",
    "IMAGE_WIDTH": "1024",
    "IMAGE_HEIGHT": "576"
  },
  "secrets": {
    "required": ["CF_ACCOUNT_ID", "CF_API_TOKEN", "CLIENT_API_KEY"]
  }
}
```

The example declares names only; it does not contain secret values or implement an AI endpoint. Confirm the current model identifier and its input/output schema before using it. Wrangler config options can change, so validate the file with your installed Wrangler version.

## 6. What to change when you want this repository to call your Worker

Creating/deploying the Worker is only the Cloudflare side. To route the AI Video Experiment through it, you would also need to:

1. Implement and deploy an endpoint in the Worker that authenticates the caller, validates the prompt and dimensions, calls the selected Workers AI model, and returns the image in a response format the Python client understands.
2. Decide whether the Worker or GitHub Actions owns the Cloudflare credentials. Prefer keeping `CF_API_TOKEN` only as a Worker secret if the Worker is the gateway.
3. Add a client-side secret (for example `CF_WORKER_API_KEY`) to GitHub Actions so only your workflow can call the gateway.
4. Modify `scripts/make_art.py` so `cf_image_cheap()` calls the Worker URL rather than constructing the Cloudflare account REST endpoint. Update request headers/body and response decoding to match the Worker contract.
5. Add the Worker URL and client key to GitHub repository secrets (for example `CF_WORKER_URL` and `CF_WORKER_API_KEY`) and pass them into the image-generation step in `.github/workflows/ai-video-test.yml`.
6. Test a single image, then a complete run. Check non-200 responses, timeouts, authentication failures, image content type, output dimensions and provider usage.

**Do not change the current Python endpoint to a guessed Worker URL.** First deploy and test the Worker endpoint, define its request/response contract, then update the Python caller and workflow secrets together. No Worker gateway is currently deployed by this repository.

## 7. Common Worker changes and where to make them

| What you want to change | Where to change it |
|---|---|
| Worker name, entry file, compatibility date | `wrangler.jsonc` / `wrangler.toml` |
| Request method, URL paths, validation, authentication | Worker entry file, e.g. `src/index.js` |
| AI model name, default dimensions, feature switches | Worker code and/or Wrangler `vars` |
| Cloudflare account ID/token | Worker **Secrets**, never plaintext vars |
| Custom domain or workers.dev route | Worker **Settings → Domains & Routes** or Wrangler route configuration |
| Development/staging/production settings | Wrangler environments and their separately configured secrets |
| Logs and runtime failures | Worker **Logs / Observability** and Wrangler tail |
| Deploy a code change | `npx wrangler deploy` |
| Update a secret | `npx wrangler secret put SECRET_NAME` |
| Remove a secret | `npx wrangler secret delete SECRET_NAME` |

## 8. Troubleshoot Worker deployment and requests

| Symptom | What to check |
|---|---|
| Worker URL returns 404 | Confirm the Worker deployed successfully and the workers.dev/custom-domain route is enabled and correct. |
| Deploy fails | Run Wrangler from the Worker project directory; check authentication, config syntax and the configured entry file. |
| Missing binding/secret | Check the exact binding name and configure it for the environment being deployed. Secrets are not automatically shared between environments. |
| Dashboard edit disappears | A later Wrangler deployment may overwrite dashboard configuration; keep the Wrangler project as source of truth. |
| Worker returns 401/403 | Check client authentication separately from the Cloudflare API token, and verify the token's Workers AI permissions. |
| AI request fails | Inspect Worker logs, account/model availability, request schema, quota and response handling. |
| Local works, production fails | Compare local `.dev.vars` with deployed Worker secrets and production environment configuration. |
| GitHub Actions cannot reach Worker | Check the Worker URL, route, client key secret, request contract and outbound response handling. |

Useful official references:
- [Create and deploy Workers](https://developers.cloudflare.com/workers/get-started/guide/)
- [Wrangler commands](https://developers.cloudflare.com/workers/wrangler/commands/workers/)
- [Wrangler configuration](https://developers.cloudflare.com/workers/wrangler/configuration/)
- [Environment variables](https://developers.cloudflare.com/workers/configuration/environment-variables/)
- [Secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [Workers AI](https://developers.cloudflare.com/workers-ai/)

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
8. If an individual scene request fails, the code reuses a randomly selected successful AI image for that scene. If Cloudflare fails, AI Horde and OVHcloud are attempted in order. If all providers fail for a scene, generation stops rather than substituting stickman artwork.

**Important:** the current implementation is a single-model Cloudflare integration. Despite older references to multiple/cheap image models, the active code uses only FLUX-2-KLEIN-4B. It does not automatically switch to a second Cloudflare model.

## B. Create and configure Cloudflare credentials

You need a Cloudflare account with Workers AI access.

1. Sign in to the Cloudflare dashboard.
2. Find your Cloudflare account ID in the account overview/dashboard URL or account details.
3. On the Workers AI page, select **Use REST API → Create a Workers AI API Token** and use Cloudflare's recommended token template. If you create a custom token instead, Cloudflare's current REST API guidance requires the account-level **Workers AI - Read** permission for model execution; the Workers AI onboarding page also describes a custom-token setup with **Workers AI - Read** and **Workers AI - Edit**. Prefer the official Workers AI token template, or follow the current permission guidance displayed by Cloudflare when creating the token. Do not grant unrelated account permissions or use an unrestricted Global API Key.
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
- If all three providers fail for a scene, image generation raises an error and the workflow stops.

You can adjust the six-second delay or timeout, but do not remove the delay without checking Cloudflare's current rate limits. For a robust production change, implement bounded retries with exponential backoff for transient HTTP 429 and 5xx errors, while avoiding retries for permanent authentication or invalid-request errors. Log HTTP status and a safe error summary, but never log the bearer token or full authorization headers.

If you want a different fallback policy, change the section under `# If any failed, reuse a successful image to fill the gap`. The current implementation already fails the image-generation step if all providers fail for a scene. That requires changing how `main_ai.py` handles `None` image data and how the artwork function is called. Test the full pipeline after modifying this behavior.

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
| A scene image fails | Check the Cloudflare, AI Horde and OVHcloud errors for that scene; the pipeline intentionally stops rather than substituting artwork. |

---

# 🛠️ How this repository implemented Cloudflare — exact code path and modification map

This is the implementation currently present in `main`; it is not a generic Cloudflare tutorial.

## 1. Actual request path

```text
.github/workflows/ai-video-test.yml
  └─ Generate AI Video step exposes CF_ACCOUNT_ID + CF_API_TOKEN
       └─ python main_ai.py
            └─ scripts/make_art.py: generate_all_ai_images()
                 ├─ build_prompt(scene["visual"])
                 ├─ cf_image_cheap(prompt)
                 │    └─ POST Cloudflare Workers AI REST endpoint
                 └─ collect image bytes per scene
                      └─ make_scene_art() resizes and overlays title/caption
```

There is no separate Worker URL or custom Worker source in this request path. The Cloudflare feature used here is **Workers AI**, called directly through its account REST endpoint.

## 2. What each part of the code does

| Code location | Current implementation | Change it when you want to… |
|---|---|---|
| `.github/workflows/ai-video-test.yml` → `Generate AI Video` env | Maps GitHub secrets into `CF_ACCOUNT_ID` and `CF_API_TOKEN` | Rename secrets or change where credentials are supplied |
| `scripts/make_art.py` → `CF_ACCOUNT_ID`, `CF_API_TOKEN` | Reads environment variables with `os.getenv()` | Change credential variable names (also update workflow and local environment) |
| `scripts/make_art.py` → `CF_URL_CHEAP` | Builds `https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}` | Change the account API route or model identifier |
| `build_prompt()` | Normalizes whitespace, removes double quotes, truncates scene visual text to 250 characters, appends `STYLE` | Change prompt length, cleanup or shared visual style |
| `cf_image_cheap()` | Checks credentials, sends multipart POST with Bearer token, prompt, width 1024, height 576; timeout 120 seconds | Change authentication, request fields, dimensions, timeout or response handling |
| `generate_all_ai_images()` | Processes scenes sequentially, waits 6 seconds between calls, records failures and reuses a random successful image for failed scenes | Change concurrency, pacing, retry policy and failed-scene behavior |
| `make_scene_art()` | Opens returned bytes with Pillow, resizes to output size, draws title/caption bars and saves the final scene image | Change image composition and overlays |
| 

## 3. Current API request, in plain language

For each scene, the script sends an HTTPS **POST** request to:

```text
https://api.cloudflare.com/client/v4/accounts/<CF_ACCOUNT_ID>/ai/run/@cf/black-forest-labs/flux-2-klein-4b
```

It authenticates with:

```http
Authorization: Bearer <CF_API_TOKEN>
```

The body is multipart form data containing `prompt`, `width=1024` and `height=576`. The code uses `requests.post(..., files=form_data, timeout=120)`. It raises on HTTP errors. If the response content type starts with `image/`, it uses the response body directly; otherwise it parses JSON and base64-decodes the `image` field from `result` (or the top-level object).

The active model is configured in the endpoint string, not in `config.json`. Changing `config.json` does not change the Cloudflare model.

## 4. Common modifications — exact edits

### Change the image model

1. Check the current [Workers AI model catalogue](https://developers.cloudflare.com/workers-ai/models/) and confirm the model is enabled for your account.
2. In `scripts/make_art.py`, replace the model identifier in `CF_URL_CHEAP`.
3. Check that model's input schema and response format. If different, change `form_data` and the response decoder in `cf_image_cheap()` too.
4. Run one test generation before running the full 47-scene experiment.

### Change image dimensions

Edit `width` and `height` in `form_data` inside `cf_image_cheap()`. Keep the model's supported dimensions and aspect ratio in mind. The returned image is subsequently resized to the root `config.json` output dimensions in `make_scene_art()`; these are two separate dimension settings.

### Change style or prompt content

- Edit `STYLE` near the top of `scripts/make_art.py` to change the shared style for every scene.
- Edit `build_prompt()` to change text cleanup, truncation (currently 250 characters), prompt ordering or additional instructions.
- Edit `scene.get("visual", "science illustration")` inside `generate_all_ai_images()` if you want a different fallback field/default. If you change the story JSON schema, also update the story generator and consumers.

### Change request pacing, timeout or add retries

- Delay: edit `time.sleep(6)` in `generate_all_ai_images()`. The delay currently occurs between scene requests, not after the final request.
- Timeout: edit `timeout=120` in `cf_image_cheap()`.
- Retries: there is currently **no explicit retry loop**. Add bounded retries with backoff around the request, and avoid retrying permanent errors such as invalid credentials or unsupported model names.
- Concurrency: calls are currently sequential. Introducing parallel requests changes rate-limit pressure and should be tested against the account's current limits.

### Change what happens when an image request fails

Today, failed requests are stored as `None`. If at least one scene succeeded, each failed slot receives a randomly chosen successful image. If all three providers fail for a scene, `generate_all_ai_images()` raises an error and the workflow stops. Provider order, retries, request pacing and fail-fast behavior are configured in `generate_all_ai_images()`.

### Change title/caption overlays

Edit `make_scene_art()` in `scripts/make_art.py`: title truncation (58 characters), blue title rectangle, black caption rectangle, caption wrapping (75-character line threshold, at most two lines), font sizes and coordinates. These overlays are added after Cloudflare returns the image; they are not part of the model prompt.

## 5. Credential rotation and testing

- Create/rotate the Cloudflare API token in Cloudflare; give it only the Workers AI permissions required by the current API guidance.
- Update repository **Settings → Secrets and variables → Actions → Secrets → `CF_API_TOKEN`**. Update `CF_ACCOUNT_ID` only if using a different Cloudflare account.
- For local runs, export both environment variables in the shell. Do not add them to source code or `config.json`.
- Run **Actions → AI Video Experiment → Run workflow** and inspect the `Generate AI Video` logs. Check for `Klein OK`, `Klein failed`, and `Filled with a random AI image`.
- Inspect generated scene images and the final video; a successful HTTP request alone does not guarantee the composition is what you want.

If you decide to put a custom Cloudflare Worker in front of Workers AI later, that is a new architecture: deploy and test the Worker endpoint first, then change `CF_URL_CHEAP`/request handling and the workflow secrets to call it. The current repository does not have that gateway.

---

# 📲 Telegram — complete bot setup

## 🔧 How the Telegram bot is actually implemented in this repository

There are two different Telegram implementations. They share repository secrets, but they do not share the same message-processing code.

### A. Science Channel incoming-image bot

The incoming bot is a **GitHub Actions scheduled poller**, not a continuously running Telegram server or webhook.

```text
Telegram user sends image / ZIP / command
  └─ Telegram Bot API stores an update
       └─ .github/workflows/telegram-image-receiver.yml (every 5 minutes)
            └─ science-channel/scripts/telegram_image_receiver.py
                 ├─ getUpdates: fetch new messages using saved offset
                 ├─ compare message.chat.id with TELEGRAM_CHAT_ID
                 ├─ /start, /help, /episode: help and episode selection
                 ├─ getFile + file download: fetch image or ZIP
                 ├─ save numbered scene files in episode/images/incoming/
                 ├─ create READY.txt when all 48 slots exist
                 └─ save telegram-bot-state.json
                      └─ workflow commits images + state to main
                           └─ push triggers free-science-visuals.yml renderer
```

The important implementation details are:

- `TOKEN`, `CHAT_ID` and `API` are initialized at the top of `science-channel/scripts/telegram_image_receiver.py` from `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- `api()` calls `https://api.telegram.org/bot<TOKEN>/<method>` with Python `requests`, checks HTTP status and Telegram's JSON `ok` flag, then returns `result`.
- `getUpdates` uses the saved `offset`. After each update, the script stores `update_id + 1` so already handled updates are not processed again.
- The receiver only processes messages where `str(message.chat.id) == TELEGRAM_CHAT_ID`. This is the incoming chat allowlist.
- `getFile` retrieves Telegram's file path; the script downloads the bytes from Telegram's file endpoint.
- Images are assigned to the next missing scene slot based on arrival order. A ZIP is sorted alphabetically (case-insensitive) and must contain exactly 48 supported images.
- `science-channel/telegram-bot-state.json` stores the offset and selected episode path. It is committed with received files.
- The workflow explicitly checks out and pushes **main**. Keep this branch behavior unchanged.

### B. Outgoing Telegram messages and videos

Outgoing messages use three mechanisms:

| Sender | Implementation | What it sends |
|---|---|---|
| Science Channel planner | Direct `curl` to Telegram `sendDocument` in `.github/workflows/science-channel-daily-planner.yml` | `image-prompts.md` with an episode caption |
| Science Channel renderer | `PonomarevDA/telegram-upload@v1` in `.github/workflows/free-science-visuals.yml` | Final episode MP4 |
| Root AI Video Experiment | `PonomarevDA/telegram-upload@v1` in `.github/workflows/ai-video-test.yml` | Root experiment MP4 |

The planner's direct Bot API request uses `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, the `sendDocument` method and multipart fields `chat_id`, `document` and `caption`. The two video workflows pass `bot_token`, `chat_id`, `files` and `message` to the upload action.

## 🧰 Change the existing Telegram bot — exact code locations

| What you want to change | Exact location | What to edit |
|---|---|---|
| Replace the bot account/token | GitHub secret `TELEGRAM_BOT_TOKEN` | Create/revoke token with @BotFather, then replace the secret; no code edit needed |
| Change the destination or incoming allowlist chat | GitHub secret `TELEGRAM_CHAT_ID` | Set the new numeric chat ID; receiver and outgoing messages use this value |
| Change incoming poll frequency | `.github/workflows/telegram-image-receiver.yml` | Edit `schedule.cron`; current value is `*/5 * * * *` (UTC) |
| Change receiver runtime/timeout | Same receiver workflow | Edit Python version, dependency install or `timeout-minutes` |
| Change bot commands/help replies | `science-channel/scripts/telegram_image_receiver.py` → `main()` | Edit the `/start`, `/help` and `/episode` command branches |
| Change which chat is allowed | Same script → `CHAT_ID` and message chat comparison | Current behavior is exact equality with `TELEGRAM_CHAT_ID`; update deliberately if supporting multiple chats |
| Change auto-selected episode | Same script → `newest_episode()` and selection logic at start of `main()` | Change sorting/selection policy; episode must exist on main |
| Change supported image formats | Same script → `image_payload()`, `scene_numbers()` and ZIP suffix filter | Update all format checks consistently |
| Change image count from 48 | Receiver script, planner, ZIP importer, settings, renderer and prompt docs | 48 is a pipeline-wide contract; do not change only the receiver |
| Change individual/ZIP size limits | Same script → checks using `20 * 1024 * 1024` and `50 * 1024 * 1024` | Change limits consistently with Telegram's current Bot API limits |
| Change polling offset or selected episode persistence | `load_state()`, `save_state()`, `telegram-bot-state.json` | Change carefully; resetting offset can replay old updates |
| Change prompt document text/caption | `.github/workflows/science-channel-daily-planner.yml` | Edit the `curl` `caption` and `sendDocument` fields |
| Change Science Channel video caption | `.github/workflows/free-science-visuals.yml` | Edit the upload action's `message` |
| Change root experiment video caption | `.github/workflows/ai-video-test.yml` | Edit the upload action's `message` |
| Change video delivery failure behavior | Relevant workflow YAML | Change `continue-on-error` or step order only after considering artifact and cleanup behavior |
| Change staged ZIP import rules | `science-channel/scripts/import_telegram_zip.py` and `.github/workflows/telegram-zip-import.yml` | Change archive validation, paths, limits, token and workflow inputs together |

### Change the bot's reply text

Open `science-channel/scripts/telegram_image_receiver.py` and edit the strings passed to `send(...)`. The `send()` helper calls Telegram `sendMessage` using the configured chat ID. Keep replies short enough for Telegram and do not include secrets or private workflow data.

### Change outgoing video messages

Open the relevant workflow and edit the `message:` field under `PonomarevDA/telegram-upload@v1`. There are two separate video senders: `free-science-visuals.yml` for Science Channel and `ai-video-test.yml` for the root AI experiment. Changing one does not change the other.

### Add another command

Add a command branch in `main()` before the image-download handling. Parse and validate the command text, send the response with `send()`, and use `continue` so the command is not mistaken for an image upload. If the command changes the selected episode or another persistent setting, update `state` and set `changed = True` so the workflow commits the updated state file.

### Important behavior when changing Telegram code

- The receiver runs only when the GitHub Actions poller runs; a message can wait up to roughly one poll interval or longer if Actions is delayed.
- Telegram updates are consumed by the offset. Do not reset `telegram-bot-state.json` unless you intend to reprocess pending/old messages.
- A newer episode can automatically replace an older selected episode. Confirm the bot's selection reply before uploading.
- The receiver commits to `main`; the resulting push triggers rendering when incoming images/READY are changed.
- Science Channel cleanup runs only after successful video delivery. Do not remove this condition unless you deliberately want to delete source images even when Telegram delivery fails.
- The root AI experiment's Telegram send currently runs before artifact upload and is not `continue-on-error`; a send failure can stop later steps. Science Channel artifact upload occurs before Telegram delivery and its send step is non-blocking.

---

, upload, delivery and modification guide

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
2. Send a fresh message such as `/start` to the bot. Then, in a private terminal where you have set `TELEGRAM_BOT_TOKEN`, run `curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"`. Find the newest update's `message.chat.id`. If the receiver workflow polls at the same time, it may consume the update first; temporarily disable/pause the receiver schedule or send another message and inspect updates promptly. Keep the token private. Do not paste a tokenized API URL or the full response into a public issue, repository or chat.
3. Copy the numeric chat ID exactly. Group chat IDs are often negative; do not remove a minus sign.
4. In GitHub, open **Settings → Secrets and variables → Actions → Secrets**.
5. Create/update:
   - `TELEGRAM_BOT_TOKEN` = token from BotFather.
   - `TELEGRAM_CHAT_ID` = numeric private-chat or group-chat ID.
6. Save both as repository **Secrets**.

The same names are referenced by the planner, receiver and video workflows. If the token is changed, update the one repository secret rather than editing Python or YAML files.

### How the code uses the credentials

The image receiver reads both environment variables in `science-channel/scripts/telegram_image_receiver.py`. It uses Telegram Bot API methods `getUpdates`, `getFile`, `sendMessage` and the file download URL. The planner sends its prompt document with `sendDocument`. The video workflows use the `PonomarevDA/telegram-upload@v1` GitHub Action with the same token and chat ID. See the official [Telegram Bot API reference](https://core.telegram.org/bots/api) for method parameters, file handling, update polling and platform limits.

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

# GitHub Actions workflow index

This directory contains the ten workflows currently present in `.github/workflows/`. Each production workflow has its own operating guide. Read the guide before changing triggers, secrets, inputs, concurrency, artifacts, publishing, or cleanup behavior.

## Individual workflows

| Actions display name | Workflow file | Trigger | Purpose | Detailed guide |
|---|---|---|---|---|
| 💡 AI Chat Videos | [ai-roast-studio.yml](ai-roast-studio.yml) | Telegram bot dispatch or video added to `ai-chat-videos/uploads/` on `main` | Edits a recorded conversation video, renders an MP4, uploads an artifact and attempts Telegram delivery; GitHub-upload cleanup follows artifact creation. | [AI Chat Videos](../../ai-chat-videos/README.md) |
| AI Story & Science Video Creator | [ai-story-science-video.yml](ai-story-science-video.yml) | Daily schedule and manual | Standalone Gemini story/science video: 48 scenes, anonymous image-provider fallbacks, Edge TTS, word-level karaoke captions and MP4 delivery. | [AI Story & Science Video Creator](../../ai-story-science-video/README.md) |
| AI Video Experiment | [ai-video-test.yml](ai-video-test.yml) | Daily schedule and manual | Separate Gemini/Cloudflare image experiment with AI Horde and OVH fallbacks, narration and FFmpeg rendering. | [AI Video Experiment](../../ai-video-experiment/README.md) |
| Free Science Visuals — Render Ready Episode | [free-science-visuals.yml](free-science-visuals.yml) | Incoming image/READY marker push or manual | Validates a Science Channel episode's 48 images, generates narration, renders karaoke subtitles, delivers the MP4 and performs post-delivery cleanup. | [Free Science Visuals renderer](guides/free-science-visuals.md) |\n| Free 3D Explainer Video Factory | [free-3d-explainer.yml](free-3d-explainer.yml) | Manual | Generates a 3–8 minute science explainer using free anonymous LLM fallback, procedural Blender 3D stills, free TTS and FFmpeg; uploads MP4 and production metadata. | This workflow index |
| Science Channel — Daily Gemini Planner | [science-channel-daily-planner.yml](science-channel-daily-planner.yml) | Daily schedule and manual | Creates a fresh Science Channel episode package with metadata, narration, 48 scene records and image prompts. | [Daily Gemini Planner](guides/science-channel-daily-planner.md) |
| Telegram Image Receiver | [telegram-image-receiver.yml](telegram-image-receiver.yml) | Cloudflare Worker inbox push or manual maintenance run | Downloads and validates Telegram image/ZIP uploads, fills episode image slots and dispatches the renderer when an episode becomes ready. | [Telegram Image Receiver](guides/telegram-image-receiver.md) |
| Telegram ZIP Import | [telegram-zip-import.yml](telegram-zip-import.yml) | Manual with `episode_path` and `zip_path` | Safely imports a ZIP already staged in the repository into one episode and creates its READY marker. | [Telegram ZIP Import](guides/telegram-zip-import.md) |
| Telegram Failed Workflow Alerts | [telegram-failure-alerts.yml](telegram-failure-alerts.yml) | Completion event from monitored workflows; sends only on failure | Sends a Telegram failure notice with workflow name, run number, branch, repository and run URL. | [Telegram Failed Workflow Alerts](guides/telegram-failure-alerts.md) |
| Validate GitHub Actions workflows | [validate-workflows.yml](validate-workflows.yml) | Relevant push/PR changes or manual | Runs actionlint, Python syntax compilation and Cloudflare Worker JavaScript syntax validation. | [Workflow validation](guides/validate-workflows.md) |

## Choose the right pipeline

- **Science Channel:** planner → create/review images → Telegram Image Receiver or Telegram ZIP Import → Free Science Visuals renderer. These episode and upload workflows operate on `main`.
- **AI Story & Science Video Creator:** standalone one-click story/science generation. It does not create a Science Channel episode package.\n- **Free 3D Explainer Video Factory:** independent manual generator using procedural Blender scenes and free-service fallbacks; it does not use the 48-image Telegram episode pipeline.
- **AI Video Experiment:** a separate legacy experiment with its own root-level configuration and topic history.
- **AI Chat Videos:** a separate recorded-conversation editor.
- **Telegram Failed Workflow Alerts:** notification-only; it does not rerun or repair failed jobs.
- **Validate Workflows:** static checks only; it does not prove external services or full media generation work.

## Secrets and safety

1. Store credentials only in **Repository → Settings → Secrets and variables → Actions**. Never place tokens in YAML, scripts, generated media or README files.
2. The Science Channel Telegram webhook is owned by `cloudflare-worker.js`. Do not add Telegram polling or call `deleteWebhook` in the receiver.
3. Keep the Science Channel planner, receiver, ZIP importer and renderer on `main`; do not mix them with the `adaptive-cinematic-effects` branch.
4. Treat ZIPs and user uploads as untrusted input. Preserve path traversal checks, file-count/size limits and supported-format validation.
5. Preserve retry, checkpoint, artifact, delivery and cleanup ordering when editing a production workflow.
6. Review third-party Action pins before updating them. Keep least-privilege permissions and concurrency protections.

## Verification checklist

- Run **Validate GitHub Actions workflows** after changing workflow YAML, Python entry points or the Cloudflare Worker.
- Run the affected workflow manually and inspect its logs, artifacts, Telegram result and repository side effects.
- A green static validation run is not an end-to-end test. It does not guarantee Gemini/image-provider quotas, Telegram delivery, successful encoding or authorized Git pushes.
- Check the guide for the individual workflow for expected outputs, recovery steps and known limitations.

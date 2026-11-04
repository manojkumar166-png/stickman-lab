# GitHub Actions workflow index

This directory contains the repository's GitHub Actions workflows. Open the YAML file to inspect or change its triggers, inputs, secrets, runner, timeouts, artifact settings and delivery steps.

## Workflow list

| Actions display name | Workflow file | What it does | Detailed guide |
|---|---|---|---|
| AI Story & Science Video Creator | [ai-story-science-video.yml](ai-story-science-video.yml) | One-click Gemini-generated topic, 48 scene images using free anonymous providers, narration, subtitles and final MP4. No manual inputs. | [AI Story & Science Video Creator guide](../../ai-story-science-video/README.md) |
| AI Story Image Fallback Test | [ai-story-image-fallback-test.yml](ai-story-image-fallback-test.yml) | Manually tests AI Horde → Vexa HD/FLUX → Pollinations and uploads the first valid PNG. | [Image fallback test guide](guides/ai-story-image-fallback-test.md) |
| AI Video Experiment | [ai-video-test.yml](ai-video-test.yml) | Separate legacy Gemini + Cloudflare Workers AI image generator, narration and final video. | [AI Video Experiment guide](../../ai-video-experiment/README.md) |
| Science Channel — Daily Gemini Planner | [science-channel-daily-planner.yml](science-channel-daily-planner.yml) | Creates a new Science Channel episode package with 48 scenes and image prompts. | [Daily Planner guide](guides/science-channel-daily-planner.md) |
| Telegram Image Receiver | [telegram-image-receiver.yml](telegram-image-receiver.yml) | Receives images/ZIPs forwarded by the Cloudflare Telegram webhook and fills an episode's incoming image slots. | [Telegram Image Receiver guide](guides/telegram-image-receiver.md) |
| Telegram ZIP Import | [telegram-zip-import.yml](telegram-zip-import.yml) | Imports a ZIP staged in the repository into a selected Science Channel episode. | [Telegram ZIP Import guide](guides/telegram-zip-import.md) |
| 💡 AI Chat Videos | [ai-roast-studio.yml](ai-roast-studio.yml) | Automatically edits videos submitted through the Telegram bot or committed under `ai-chat-videos/uploads/`; saves an edited artifact, sends it to Telegram and cleans GitHub uploads from the current branch after artifact creation. | [AI Chat Videos guide](../../ai-chat-videos/README.md) |
| Free Science Visuals — Render Ready Episode | [free-science-visuals.yml](free-science-visuals.yml) | Validates 48 episode images, renders the narrated video with karaoke captions, sends Telegram video and cleans uploads after successful delivery. | [Renderer guide](guides/free-science-visuals.md) |
| Validate Workflows | [validate-workflows.yml](validate-workflows.yml) | Runs actionlint, Python syntax compilation and Cloudflare Worker JavaScript syntax checks. | [Validation guide](guides/validate-workflows.md) |

## Which README should I read?

- **Science Channel pipeline:** the planner, Telegram receiver, ZIP importer and renderer work together, so their shared instructions are in [science-channel/README.md](../../science-channel/README.md).
- **AI Story & Science Video Creator:** its standalone guide is [ai-story-science-video/README.md](../../ai-story-science-video/README.md).
- **AI Video Experiment:** its standalone guide is [ai-video-experiment/README.md](../../ai-video-experiment/README.md).
- **AI Chat Videos:** its upload methods, workflow triggers, artifact/Telegram delivery, cleanup behavior and public-repository warning are in [ai-chat-videos/README.md](../../ai-chat-videos/README.md).
- **Repository overview and customization map:** [root README.md](../../README.md).

Every workflow has a linked detailed guide. The Science Channel overview remains useful for understanding how the planner, Telegram intake, ZIP importer and renderer fit together.

## Safe editing checklist

1. Read the guide linked in the table before changing a workflow.
2. Keep secrets in GitHub repository Settings → Secrets and variables → Actions. Never paste tokens into YAML or README files.
3. Pin third-party Actions to reviewed full commit SHAs; keep the upstream version in a comment and update pins only after reviewing the release.
4. Check whether another workflow relies on the same folder, artifact, READY marker, Telegram bot, concurrency group or topic-history file.
5. Preserve existing fallback, upload, delivery and cleanup behaviour unless the change specifically requires modifying it.
6. Commit to `main` only when the change is intended for the live pipeline; otherwise use a branch and review the diff.
7. Let the validation workflow pass after code/workflow changes. Then run the affected production workflow from Actions and inspect its logs and artifacts. Static validation does not prove that external APIs, Telegram delivery or a full video render succeeded.

## Individual workflow guides

- [AI Story & Science Video Creator](../../ai-story-science-video/README.md)
- [AI Story image fallback test](guides/ai-story-image-fallback-test.md)
- [AI Video Experiment](../../ai-video-experiment/README.md)
- [Daily Gemini Planner](guides/science-channel-daily-planner.md)
- [Telegram Image Receiver](guides/telegram-image-receiver.md)
- [Telegram ZIP Import](guides/telegram-zip-import.md)
- [AI Chat Videos](../../ai-chat-videos/README.md)
- [Free Science Visuals renderer](guides/free-science-visuals.md)
- [Validate Workflows](guides/validate-workflows.md)

Each guide documents its workflow's trigger, execution steps, secrets/variables, outputs, customization points, troubleshooting and rollback procedure.

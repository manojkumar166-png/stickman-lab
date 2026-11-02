# GitHub Actions workflow index

This directory contains the repository's GitHub Actions workflows. Open the YAML file to inspect or change its triggers, inputs, secrets, runner, timeouts, artifact settings and delivery steps.

## Workflow list

| Actions display name | Workflow file | What it does | Detailed guide |
|---|---|---|---|
| AI Story & Science Video Creator | [ai-story-science-video.yml](ai-story-science-video.yml) | One-click Gemini-generated topic, 48 scene images using free anonymous providers, narration, subtitles and final MP4. No manual inputs. | [AI Story & Science Video Creator guide](../../ai-story-science-video/README.md) |
| AI Video Experiment | [ai-video-test.yml](ai-video-test.yml) | Separate legacy Gemini + Cloudflare Workers AI image generator, narration and final video. | [AI Video Experiment guide](../../AI_README.md) |
| Science Channel — Daily Gemini Planner | [science-channel-daily-planner.yml](science-channel-daily-planner.yml) | Creates a new Science Channel episode package with 48 scenes and image prompts. | [Science Channel guide](../../science-channel/README.md) |
| Telegram Image Receiver | [telegram-image-receiver.yml](telegram-image-receiver.yml) | Receives images/ZIPs forwarded by the Cloudflare Telegram webhook and fills an episode's incoming image slots. | [Science Channel guide](../../science-channel/README.md) |
| Telegram ZIP Import | [telegram-zip-import.yml](telegram-zip-import.yml) | Imports a ZIP staged in the repository into a selected Science Channel episode. | [Science Channel guide](../../science-channel/README.md) |
| Free Science Visuals — Render Ready Episode | [free-science-visuals.yml](free-science-visuals.yml) | Validates 48 episode images, renders the narrated video with karaoke captions, sends Telegram video and cleans uploads after successful delivery. | [Science Channel guide](../../science-channel/README.md) |
| Validate Workflows | [validate-workflows.yml](validate-workflows.yml) | Runs repository workflow configuration checks. | This page |

## Which README should I read?

- **Science Channel pipeline:** the planner, Telegram receiver, ZIP importer and renderer work together, so their shared instructions are in [science-channel/README.md](../../science-channel/README.md).
- **AI Story & Science Video Creator:** its standalone guide is [ai-story-science-video/README.md](../../ai-story-science-video/README.md).
- **AI Video Experiment:** its standalone guide is [AI_README.md](../../AI_README.md).
- **Repository overview and customization map:** [root README.md](../../README.md).

There is not one README per YAML file today. Related workflows share a pipeline guide to avoid duplicating setup and operational instructions.

## Safe editing checklist

1. Read the guide linked in the table before changing a workflow.
2. Keep secrets in GitHub repository Settings → Secrets and variables → Actions. Never paste tokens into YAML or README files.
3. Check whether another workflow relies on the same folder, artifact, READY marker, Telegram bot, concurrency group or topic-history file.
4. Preserve existing fallback, upload, delivery and cleanup behaviour unless the change specifically requires modifying it.
5. Commit to `main` only when the change is intended for the live pipeline; otherwise use a branch and review the diff.
6. Run the affected workflow from Actions and inspect its logs and artifacts. A successful commit does not prove an end-to-end workflow run succeeded.

## AI Story & Science Video Creator: one-click defaults

The current workflow has no manual dispatch inputs. It runs with 48 scenes, lets Gemini invent the topic from root `topics.txt`, and uses `en-US-AndrewMultilingualNeural`.

To change these defaults, edit [ai-story-science-video.yml](ai-story-science-video.yml) and find the Python command:

```bash
python -u scripts/ai_story_video.py --topic "" --scenes 48 --voice "en-US-AndrewMultilingualNeural"
```

- Change `--scenes 48` to another supported count (4–48).
- Change the `--voice` value to another supported Edge TTS voice ID.
- Leave `--topic ""` blank for Gemini to invent a fresh topic. To force a topic, put the desired text between the quotes.
- Edit root `topics.txt` to change the topic inspiration library.
- Edit `scripts/ai_story_video.py` to change prompts, image providers, image quality, provider order, retry/pacing logic or FFmpeg rendering.

See the [complete guide](../../ai-story-science-video/README.md) for the image-provider chain, free/no-card safeguards, model variables, troubleshooting and output details.

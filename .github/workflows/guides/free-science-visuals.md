# Free Science Visuals — Render Ready Episode

Workflow: [free-science-visuals.yml](../free-science-visuals.yml)  
Renderer implementation: [render_episode.py](../../../science-channel/scripts/render_episode.py)  
Shared captions helper: [karaoke_subtitles.py](../../../science-channel/scripts/karaoke_subtitles.py)

## Purpose and triggers

This workflow validates uploaded scene images, generates narration, renders the episode video, burns karaoke captions, uploads the final MP4 artifact and attempts Telegram delivery.

It starts when a push to `main` adds/modifies files under `science-channel/daily-episodes/**/images/incoming/**` (except `.gitkeep`) or a `READY.txt` marker. It can also be started manually from **Actions → Free Science Visuals — Render Ready Episode** with an optional `episode_path`.

For a manual run:
- Supply the exact episode folder, e.g. `science-channel/daily-episodes/2026-10-30/episode-001`; or
- Leave it blank to select the newest episode with a READY marker or incoming images.

For push-triggered runs, exactly one changed episode must be identifiable. If a push affects multiple episodes, the workflow stops and asks you to run it manually with the intended path. Deletion-only cleanup pushes are intentionally ignored.

## How it works

1. Checks out `main`, installs Python 3.11, FFmpeg, DejaVu fonts, Edge TTS and faster-whisper; caches the Whisper model.
2. Resolves and validates the episode path and requires `episode.json`.
3. Runs `science-channel/scripts/render_episode.py`, which validates the episode metadata, ordered scene records, script sections and incoming images; it supports either one ZIP archive or individual image files, not both together.
4. The renderer normalizes images to 1280×720, creates narration from the episode's `script.md` using settings in `science-channel/settings.json`, aligns word timestamps with Whisper and renders the final video with karaoke subtitles.
5. The workflow derives the final MP4 filename and artifact name from the episode title, then uploads only the final MP4 as a 2-day artifact.
6. It attempts to send the MP4 to Telegram. This step is non-blocking.
7. **Only if Telegram upload succeeds**, it deletes all files in the episode's `images/incoming/` except `.gitkeep`, removes `READY.txt`, commits that cleanup and pushes it to `main`.

Timeout: 90 minutes. It shares the `stickman-lab-main-writer` concurrency group with other main-branch writers.

## Required configuration

| Name | Type | Required | Purpose |
|---|---|---:|---|
| `TELEGRAM_BOT_TOKEN` | GitHub Secret | For delivery/alerts | Sends the final MP4 and failure alerts |
| `TELEGRAM_CHAT_ID` | GitHub Secret | For delivery/alerts | Telegram destination |

No Gemini key is used by this rendering workflow. The episode package must already exist on `main`. Rendering settings such as voice and speech rate are read from `science-channel/settings.json`.

## Input contract

The episode folder must include the files required by the renderer, including:
- `episode.json` with a title and scene count;
- `scenes.json` with exactly the expected ordered scene records;
- `script.md` with one non-empty `## Scene N` narration section per scene;
- either exactly the required number of supported individual images or one ZIP containing that number of images in `images/incoming/`.

The current pipeline defaults to 48 scenes. The renderer validates image files and normalizes them before narration/rendering. Do not mix a ZIP and individual images in the same incoming folder.

## How to change it

| Desired change | Edit |
|---|---|
| Change watched folders or manual input | Workflow `on.push.paths` / `workflow_dispatch.inputs`. Keep the trigger aligned with where uploads are stored. |
| Change rendering rules, image naming/order, validation, TTS retries or FFmpeg render | `science-channel/scripts/render_episode.py`. |
| Change voice, speech rate or scene-count defaults | `science-channel/settings.json` and the episode metadata/planner contract. |
| Change karaoke caption timing/style | `science-channel/scripts/karaoke_subtitles.py` and the workflow's caption step. |
| Change final filename/artifact naming or retention | Artifact-resolution and upload steps in the workflow. |
| Change Telegram caption/destination | Update the Telegram secrets or the upload action's `message` input. |
| Change cleanup behavior | Review the Telegram step outcome condition and the complete cleanup step. Treat this as destructive behavior. |
| Change timeout/Python/tool setup | Corresponding YAML job fields and install steps. |

If you change the scene count, coordinate the planner, Telegram receiver, ZIP importer, READY marker, renderer and all documentation. A partial count change will make otherwise valid uploads fail validation.

## Important cleanup behavior

The source uploads are deleted from Git only after Telegram video delivery reports success. If Telegram delivery fails, cleanup is skipped and the uploaded images/ZIP and READY marker remain available for another attempt. The final MP4 artifact can still be available even if Telegram delivery fails.

Do not move cleanup before delivery or remove its success condition unless you explicitly want to risk deleting the only committed source images before the video reaches Telegram. Download important artifacts; this workflow retains them for only two days.

## Troubleshooting

- **Workflow does not trigger:** verify the push is on `main` and includes a non-`.gitkeep` incoming file or a READY marker.
- **Ambiguous push:** multiple episode folders changed; use manual dispatch with the exact `episode_path`.
- **Episode metadata/scene validation error:** compare `episode.json`, `scenes.json`, `script.md` and the expected scene count.
- **Image count/format error:** upload one ZIP or the required number of individual supported images; do not mix both.
- **TTS or Whisper failure:** inspect the failing chunk/model logs and verify the runner can reach the speech/model services.
- **FFmpeg failure:** inspect the command output and verify the generated media files are valid.
- **Telegram delivery failed:** confirm both Telegram secrets, bot permissions and file size. The cleanup step should be skipped; the artifact may still be downloadable.
- **Cleanup push failed:** inspect rebase/push logs. The workflow retries; do not manually delete source images until the video has been verified.

## Rollback

This workflow can create two distinct commits: an optional cleanup commit after Telegram delivery, and any upstream upload commit that triggered the render.

- To restore incoming source files after cleanup, revert the **cleanup commit**. That commit contains deletions of incoming files and READY marker; reverting it restores those files.
- To undo an incorrect uploaded batch, identify and revert the original upload/import commit as a separate action.
- If a video was already sent, a Git revert cannot recall it from Telegram. Delete it from the chat separately if required.
- Download the final artifact before its 2-day retention expires if it must be preserved.

```bash
git checkout main
git pull --ff-only
git revert <cleanup-commit-sha>
git push origin main
```

Review the revert diff before pushing. Reverting a cleanup commit intentionally makes the incoming files/READY marker available again and may trigger another render; check the Actions run before leaving it unattended.

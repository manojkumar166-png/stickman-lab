# Telegram Image Receiver

Workflow: [telegram-image-receiver.yml](../telegram-image-receiver.yml)  
Receiver implementation: [telegram_image_receiver.py](../../../science-channel/scripts/telegram_image_receiver.py)

## Purpose and flow

This workflow processes Telegram updates staged by the repository's Cloudflare Worker. It runs when files are pushed under `.github/telegram-inbox/**`, and it can also be started manually for maintenance. A manual run does not create a Telegram update by itself.

1. Checks out `main` with full history and installs Python 3.11 plus `requests`.
2. Runs `science-channel/scripts/telegram_image_receiver.py` with the bot token and configured chat ID.
3. The receiver reads queued update JSON from `.github/telegram-inbox/`, validates the source chat and selected episode, downloads supported images/documents, and updates the episode's incoming image folder and `science-channel/telegram-bot-state.json`.
4. The receiver saves its state and removes processed inbox JSON only after the updates have been handled. The workflow stages episode changes, receiver state and inbox deletions, commits them, then fetches/rebases/pushes to `main` with up to five attempts.
5. If the selected episode now has `READY.txt`, the workflow explicitly dispatches **Free Science Visuals — Render Ready Episode** for that exact episode. This explicit dispatch is required because a push made with the workflow's `GITHUB_TOKEN` does not automatically start another workflow.

The job timeout is 45 minutes. It shares `stickman-lab-main-writer` concurrency with other main-branch writers. It needs `contents: write` to publish received files and `actions: write` to dispatch the renderer.

## Required configuration

| Name | Type | Required | Purpose |
|---|---|---:|---|
| `TELEGRAM_BOT_TOKEN` | GitHub Secret | Yes for receiving files | Authenticates Telegram Bot API downloads and replies |
| `TELEGRAM_CHAT_ID` | GitHub Secret | Yes for receiving files | Restricts accepted source chat and sets reply destination |

The Cloudflare Worker also needs its own Telegram/GitHub configuration; those Worker settings are separate from this Actions workflow. Do not paste bot tokens into code, workflow inputs or repository files.

## Important operating rules

- The receiver is webhook/inbox driven. Do **not** add Telegram `getUpdates` polling or call `deleteWebhook`; that competes with or removes the Cloudflare Worker webhook.
- The selected episode is stored in `science-channel/telegram-bot-state.json`. The receiver expects the episode package to already exist on `main`. Use the exact episode folder name, including its topic slug, in `/episode YYYY-MM-DD/episode-NNN-topic-slug`; the short `episode-NNN` form is accepted only when that exact folder exists.
- Incoming scene images are stored under the selected episode's `images/incoming/`.
- The current pipeline is built around 48 scene slots. Individual uploads are assigned to the next missing slot based on arrival order; filenames/captions do not set the scene number.
- The Cloudflare Worker queues authorized Telegram photos, JPG/PNG/WebP image documents and ZIP documents as durable JSON files in `.github/telegram-inbox/`. It uses the Telegram update ID as the filename so webhook retries do not queue the same update twice.
- Send 48 individual images, or one ZIP containing exactly 48 supported images. ZIP uploads are checked for unsafe paths, duplicate names, per-image size and total expanded size. The original ZIP is saved as `images/incoming/source-upload.zip` alongside the extracted scene images.
- The renderer ignores `source-upload.zip` as a second input archive. It remains available until Telegram confirms successful video delivery; the renderer then removes it together with the uploaded scene images. If rendering or delivery fails, the archive and images remain for recovery.
- Check the receiver script before changing accepted formats, size limits or numbering.

## How to change it

| Desired change | Edit |
|---|---|
| Change bot or destination chat | Update Actions secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; update the Cloudflare Worker configuration separately if needed. |
| Change supported image types, file limits or ZIP rules | Edit validation and download logic in `science-channel/scripts/telegram_image_receiver.py`. |
| Change scene numbering or completion behavior | Edit the receiver's scene-slot and READY-marker logic, then update the ZIP importer and renderer consistently. |
| Change episode selection or commands | Edit command handling and episode-selection helpers in the receiver script. |
| Change Python version, timeout or trigger paths | Edit the corresponding workflow keys. Preserve the inbox push trigger. |
| Change where updates are staged | Coordinate the Cloudflare Worker inbox path and this workflow's `on.push.paths` plus receiver script. |
| Change commit/retry behavior | Review the git add/commit/fetch/rebase/push block; keep the shared concurrency protection. |

Do not change only the workflow's path filter if the Worker or Python receiver still writes to the old inbox location.

## Troubleshooting

- **No workflow run after Telegram upload:** check that the Worker has a valid `GITHUB_TOKEN` with repository contents write access and committed a JSON file under `.github/telegram-inbox/` on `main`.
- **Bot does not accept an upload:** verify the sender chat ID matches `TELEGRAM_CHAT_ID`, the token is valid, and the Worker forwarded the update.
- **Episode not found:** verify the exact episode folder and `episode.json` are already on `main`; select the intended episode using the bot's supported command flow.
- **Images appear in the wrong slots:** slots are assigned by arrival order. Confirm the upload sequence and receiver state before attempting a correction.
- **Workflow cannot push:** inspect repository token permissions, branch protection and rebase output. Do not solve this with a force push.
- **Renderer did not start:** confirm the receiver commit added/modified incoming image files or `READY.txt` under the renderer's watched paths.

## Rollback

1. Identify the receiver commit from the workflow log. It may contain received images, receiver state and removal of processed inbox entries.
2. Before reverting, inspect the exact files in that commit. Reverting can restore inbox queue files as well as remove received episode changes/state, which may cause updates to be processed again.
3. Prefer a reviewed revert commit rather than resetting `main`. If only one image or episode needs correction, make a targeted corrective commit instead of reverting the entire receiver batch.
4. Re-run the receiver only after checking the inbox and selected episode state to avoid duplicate or misrouted processing.
5. A revert cannot delete a Telegram message already sent by the bot.

```bash
git checkout main
git pull --ff-only
git revert <receiver-commit-sha>
git push origin main
```

Inspect the staged diff before pushing. Keep a backup of any image files you may need before reverting a batch.

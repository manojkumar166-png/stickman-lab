# AI Roast Studio

Telegram-triggered GitHub Actions editor for recorded ChatGPT conversations.

## Flow

1. Send a supported video file to the existing Stickman Lab Telegram bot.
2. The Cloudflare Worker checks the sender and dispatches the AI Roast Studio workflow using Telegram's file identifier.
3. GitHub Actions downloads a temporary copy, runs OCR-based reaction detection, creates original reaction cards and generated sound cues, and renders a vertical 1080x1920 MP4.
4. The edited file is returned to your configured Telegram chat as a document. Sending as a document avoids Telegram's video-message re-encoding.

The original upload is never modified, committed to GitHub, or deleted from Telegram. The temporary runner copy is deleted when the job ends.

## Telegram file-size limits

The standard Telegram Bot API currently limits `getFile` downloads to 20 MB and bot uploads to 50 MB. This first version accepts source files up to 20 MB and targets edited output below 48 MB. Larger source files are rejected with an explanatory Telegram message; the original remains in your Telegram chat. Larger transfers require a separately hosted Telegram Bot API server or another private transfer service. A GitHub-hosted runner cannot act as a permanent Telegram Bot API server.

## Required GitHub Actions secrets

Repository Settings → Secrets and variables → Actions:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The existing Cloudflare Worker must retain its configured `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_WEBHOOK_SECRET`, and `GITHUB_TOKEN` with Actions write permission.

## Deploy the Telegram webhook update

The repository's `cloudflare-worker.js` will be extended to recognize video messages. After the GitHub commit, deploy the updated file to the same Cloudflare Worker currently handling the Stickman Lab bot. Keep existing Worker secrets and webhook URL. Visit the Worker's `/setup` endpoint once if webhook registration is needed.

Never paste bot tokens or GitHub tokens into repository files.

## Detection and effects

This starter uses Tesseract OCR at 1.5-second intervals and conservative keyword rules with an 8-second cooldown. It can miss jokes and may occasionally choose a poor reaction. Reaction cards and short sound cues are generated locally by the script; they are not copies of copyrighted Vine Boom/FAH recordings or third-party meme images.

## Output

- 1080 × 1920 vertical canvas with blurred background and a fitted copy of the original frame
- H.264/AAC MP4
- Reaction cards and generated sound effects when OCR text matches a rule
- Original file remains unchanged in Telegram

## Troubleshooting

- **Video too large:** standard Bot API download limit is 20 MB. The workflow will not reduce or overwrite the source to bypass it.
- **No reactions:** OCR may not recognize the text or none of the trigger phrases matched. The video still renders.
- **Delivery too large:** output is targeted below 48 MB; if it still exceeds Telegram's bot upload limit, the workflow reports failure.
- **No Telegram reply:** inspect the Actions run logs and verify the two repository secrets.

# 💡 AI Chat Videos

A GitHub Actions video editor for recorded ChatGPT conversations. It detects selected phrases visible on screen, adds original reaction cards and generated sound cues, renders a vertical MP4, and sends the result to Telegram.

**Both upload routes trigger the same editor:** Telegram uploads dispatch the workflow through the existing bot; a new video committed to `ai-chat-videos/uploads/` on `main` triggers the workflow automatically.

## Quick links

- [Upload folder in GitHub](uploads/)
- [Workflow file](../.github/workflows/ai-roast-studio.yml)
- [Python editor](telegram_chat_video.py)
- [Python dependencies](requirements.txt)
- [GitHub Actions runs](https://github.com/manojkumar166-png/stickman-lab/actions/workflows/ai-roast-studio.yml)

## 1. Ways to provide a source video

### A. Telegram — automated processing (implemented)

1. Open the existing Stickman Lab Telegram bot.
2. Choose **💡 AI Chat Videos** if the menu is shown, or follow the bot's current upload instructions.
3. Send the recording as a video or document.
4. The Cloudflare Worker validates the sender and dispatches the GitHub Actions workflow with the Telegram file ID and original filename.
5. GitHub Actions downloads a temporary copy, edits it, and sends the finished MP4 back to the configured Telegram chat.

The standard Telegram Bot API download limit is **20 MB**. This workflow rejects larger source files and reports the reason. The source message remains in Telegram.

### B. GitHub — automatic processing

1. Open [ai-chat-videos/uploads/](uploads/).
2. Select **Add file → Upload files**.
3. Choose your video and commit the upload to the repository's `main` branch.
4. Commit the upload to `main`. The `push` trigger detects the added/modified video and starts **💡 AI Chat Videos** automatically.\n5. The workflow renders the edit, uploads the edited MP4 as a GitHub Actions artifact (7-day retention), and attempts Telegram delivery.\n6. After the artifact upload succeeds, the workflow deletes the source file from the current `main` branch in a cleanup commit. One video per commit; supported extensions: MP4, MOV, M4V, WEBM, MKV and AVI.

**Public-repository warning:** because this repository is public, a GitHub-uploaded video is publicly visible as soon as the upload commit is published. The cleanup commit removes it from the latest branch contents, but the original video remains retrievable from earlier Git commits/history. Do not use the GitHub upload route for private, confidential, or personal recordings. To prevent public exposure, use Telegram or make the repository private before uploading.

GitHub also enforces file-size limits for repository files and browser uploads. For large video files, use Telegram only if within the Bot API limit, or arrange a suitable private large-file storage/transfer method.

## 2. What the editor does

1. **Input:** Telegram route downloads the file using its `file_id`; GitHub route reads the video path committed under `ai-chat-videos/uploads/`.
2. **Probe:** FFprobe reads the duration and checks whether the source has an audio stream.
3. **OCR scan:** OpenCV samples frames about every 1.5 seconds, converts them to grayscale, thresholds the image, and runs Tesseract OCR.
4. **Reaction matching:** recognized text is compared against phrase patterns in `RULES` in `telegram_chat_video.py`. A cooldown prevents rapid repeated reactions; the current scan caps detections at eight.
5. **Original overlays:** Pillow draws original reaction cards; NumPy generates short synthetic sound cues. These are created locally during the run.
6. **Render:** FFmpeg creates a 1080 × 1920 vertical composition, using a blurred fill background and a fitted foreground copy of the source. It encodes H.264 video and AAC audio at 30 fps.
7. **Save and deliver:** the rendered MP4 is uploaded as a GitHub Actions artifact retained for 7 days, then sent to Telegram as a document. The output is targeted below 48 MB to leave headroom under the bot upload limit.

If no phrase matches, the video can still render without reaction cards or added cues. OCR is heuristic: it can miss text, misread text, or match a phrase in an unintended context.

## 3. Workflow details

Workflow: [`.github/workflows/ai-roast-studio.yml`](../.github/workflows/ai-roast-studio.yml)  
Displayed name: **💡 AI Chat Videos**

### Trigger and inputs

The workflow supports two triggers: a `push` to `main` that changes a video under `ai-chat-videos/uploads/`, and `workflow_dispatch` for Telegram bot requests/manual maintenance.

| Input | Required | Purpose |
|---|---:|---|
| `telegram_file_id` | Required for a Telegram/manual dispatch | Telegram file identifier passed by the bot/Worker; not needed for GitHub folder uploads |
| `original_filename` | No | Original filename used to name the returned MP4; defaults to `chat-recording.mp4` |

For GitHub uploads, the workflow checks the push commit diff and requires exactly one added/modified video file in the upload folder. Upload one video per commit. Supported extensions: `.mp4`, `.mov`, `.m4v`, `.webm`, `.mkv`, `.avi`.

### Job steps

| Step | What happens |
|---|---|
| Checkout | Checks out the repository source code |
| System packages | Installs FFmpeg, Tesseract OCR and DejaVu fonts |
| Python setup | Uses Python 3.11 and pip dependency caching |
| Dependencies | Installs packages from `requirements.txt` |
| Source selection | Selects the changed GitHub video path or Telegram `file_id` |\n| Editor | Runs `telegram_chat_video.py` against the selected source and writes an edited MP4 in the runner temporary directory |\n| Artifact | Uploads the edited MP4 as `ai-chat-video-edited-N`, retained for 7 days |\n| Telegram delivery | Attempts to send the edited MP4 to the configured Telegram chat |\n| GitHub cleanup | For GitHub-triggered runs, deletes the uploaded source from the current branch after artifact creation succeeds |
| Failure notice | If the job fails, attempts to send a Telegram message containing the Actions run URL |

### Permissions, concurrency and runtime

- Workflow permission is `contents: write` so the GitHub-upload cleanup step can commit deletion of the processed source.\n- Runs on `ubuntu-latest`; timeout is 60 minutes.\n- GitHub-triggered uploads are cleaned from the latest `main` branch only after rendering and artifact upload succeed. If rendering or artifact upload fails, the source file remains in the branch for troubleshooting/retry.\n- **Git cleanup is not secure erasure:** the upload commit remains in public Git history. A later deletion commit does not make a public video private.
- Runs on `ubuntu-latest`.
- Job timeout is 60 minutes.
- Each run has its own concurrency group and is not configured to cancel another run.
- The source and generated intermediate files live in a temporary directory. The temporary directory is removed when the script exits.
- The original Telegram message/file is not modified or deleted.

### Start or inspect a run

1. Open [GitHub Actions — AI Chat Videos](https://github.com/manojkumar166-png/stickman-lab/actions/workflows/ai-roast-studio.yml).
2. Select **Run workflow** only if you have a valid Telegram `file_id` and the workflow input is available to you. This is mainly a maintenance/manual dispatch route; ordinary users should send the video through the bot.
3. Open the run to inspect each step's logs.
4. On success, check Telegram and open the run's **Artifacts** section to download the edited MP4. The artifact is retained for 7 days.

## 4. Required configuration

### GitHub repository secrets

Go to **Repository → Settings → Secrets and variables → Actions → Repository secrets**.

| Secret | Used by | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Editor and failure notice | Authenticates Telegram Bot API calls |
| `TELEGRAM_CHAT_ID` | Editor and failure notice | Destination chat for status, result and failure messages |

### Existing Cloudflare Worker secrets

The Telegram Worker is deployed separately from GitHub Actions. Preserve its existing configuration:

| Worker secret | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Receives and responds to Telegram updates |
| `TELEGRAM_ALLOWED_USER_ID` | Restricts who can trigger the bot workflow |
| `TELEGRAM_WEBHOOK_SECRET` | Validates the Telegram webhook |
| `GITHUB_TOKEN` | Allows the Worker to dispatch the repository workflow |

The Worker also needs the repository/workflow dispatch configuration already used by the Stickman Lab bot. Do not replace the existing Worker wholesale with a reduced sample: it also handles other bot features. Deploy Worker source changes to the existing Worker and preserve its other routes, secrets and behavior.

**Never** paste tokens into this README, Python files, workflow YAML, issue comments, or workflow inputs. If a token is exposed, revoke/rotate it at the provider and update the corresponding secret.

## 5. How to customize the editor

Make changes on a feature branch if possible, review the diff, then merge to `main`. The workflow checks out the code from the commit being run.

| Desired change | File / location | Guidance |
|---|---|---|
| Add or change trigger phrases | `telegram_chat_video.py` → `RULES` | Edit the regular expressions and reaction labels. Use raw regex strings such as `re.compile(r"\\bphrase\\b", re.I)`. |
| Change reaction-card wording | `RULES` labels | Keep labels short enough to fit the card. |
| Change scan interval | `scan()` → `t += 1.5` | Smaller intervals increase OCR work and may find more events; larger intervals are faster but can miss brief text. |
| Change repeated-reaction cooldown | `scan()` → `t - last >= 8` | Increase to reduce repeated cues; decrease for more frequent cues. |
| Change maximum reactions | `scan()` → `len(events) < 8` | Higher values can make the edit busier and increase render time. |
| Change card duration or position | `render()` overlay `start/end` and `overlay` coordinates | Keep overlay timing within the source duration and test portrait and landscape inputs. |
| Change canvas size | `render()` scale/crop filters | Update the background, foreground and crop dimensions together. |
| Change output frame rate | FFmpeg arguments in `render()` | Keep the input image-loop rate and output frame rate consistent. |
| Change sound character | `sound()` | The cues are procedurally generated; keep durations short and levels controlled. |
| Change video bitrate/size target | `render()` → `target`, `vbps`, `MAX_UPLOAD` | Do not raise the upload limit above what Telegram accepts. Re-test long videos. |
| Add Python packages | `requirements.txt` | Add pinned or bounded dependencies and verify on Python 3.11. |
| Change workflow timeout/runner/steps | `ai-roast-studio.yml` | Keep secrets in the `env` mapping; do not hard-code them. |
| Change Telegram menu, validation or dispatch | `cloudflare-worker.js` | Deploy the updated Worker separately; a GitHub commit alone does not deploy Cloudflare code. |

After changing OCR rules, test with a short non-sensitive sample containing both matching and non-matching text. Inspect the result and logs before using longer recordings.

## 6. Troubleshooting and fixes

| Symptom | Likely cause | What to check / fix |
|---|---|---|
| Bot does not show **💡 AI Chat Videos** | The currently deployed Cloudflare Worker may be older than the repository source, or Telegram menu setup has not refreshed | Check the deployed Worker version and its menu/setup route. Deploy the current Worker source without removing existing bot features. |
| Bot receives video but no Actions run appears | Worker dispatch failed, sender/chat validation rejected the update, or webhook is not reaching the Worker | Check Worker logs, allowed user ID, webhook secret, workflow filename and GitHub token permissions. |
| Actions says required input is missing | Dispatch did not include `telegram_file_id` | Confirm Worker sends the exact workflow input name and a valid Telegram file ID. |
| `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` missing | Repository secret is absent or named differently | Add the exact secret names under Settings → Secrets and variables → Actions. Secret values are not visible in workflow logs. |
| Source rejected as too large | Standard Telegram Bot API `getFile` download is limited here to 20 MB | Send a smaller/compressed copy, or implement a separately supported large-file transfer path. The original Telegram upload is left intact. |
| FFprobe cannot read the file | Unsupported, damaged or incomplete video, or a file without a valid video stream | Try a normal MP4 export and confirm it plays locally. |
| OCR detects no phrases | Text is too small, low contrast, blurred, absent at sampled moments, or not covered by the regex rules | Improve recording readability, add a carefully tested pattern, or adjust scan interval/threshold. |
| Wrong or repeated reactions | OCR misread text or a broad regex matched incidental words | Narrow the regex, increase cooldown, or reduce maximum detections. |
| FFmpeg render fails | Codec/container issue, invalid filter, or unexpected input dimensions/stream | Inspect the editor step logs; test a short MP4 and review any recent filter edits. |
| Output exceeds Telegram limit | Long video or bitrate/encoding target did not fit | Shorten the source or tune bitrate/encoding; keep the 50 MB bot limit in mind. Current code rejects output above 48 MiB. |
| Result not delivered but render seems complete | Telegram sendDocument failed, token/chat is wrong, or network/API issue | Check the editor step logs and verify bot access to the configured chat. |
| Failure message not received | Failure-notice step also failed or credentials are unavailable | Open the Actions run directly and inspect the failed step. |
| GitHub upload does not start editing | Expected in the current implementation | GitHub folder uploads are storage-only. A push-trigger workflow and local-file processing support must be implemented before this route can auto-process. |

## 7. Data handling and safety

- Telegram route: source video is downloaded to a temporary runner directory; it is not committed to GitHub and is not deleted from Telegram.
- Rendered result: sent to the configured Telegram chat; not currently committed to the repository or uploaded as an Actions artifact.
- GitHub folder route: files committed under `ai-chat-videos/uploads/` become repository content and remain in Git history unless history is rewritten. Treat this as persistent storage, not temporary upload staging.
- Public repository: anyone can view committed source videos. Consider making the repository private before uploading personal recordings.
- Keep original recordings separately if you need long-term archival. The editor does not overwrite them.

## 8. Known limitations

- GitHub-folder upload automation is not implemented yet.
- Telegram Bot API source download is limited to 20 MB in this implementation.
- The script targets output below 48 MiB; unusually long or complex recordings may still fail the size check.
- OCR rules are simple phrase matching, not semantic understanding or reliable joke detection.
- Up to eight reaction events are added per video.
- The current workflow has no scheduled trigger and no automatic retry policy.
- The edited MP4 artifact is retained for 7 days; the source video is not uploaded as an artifact.

## 9. Safe change checklist

Before merging changes:

- [ ] Confirm no secrets or private recordings are included in the commit.
- [ ] Check workflow YAML indentation and input names.
- [ ] Keep the workflow's Telegram secret names consistent with repository settings.
- [ ] Keep the original source file untouched.
- [ ] Test with a short sample and inspect the returned MP4.
- [ ] Check Actions logs and Telegram delivery.
- [ ] If `cloudflare-worker.js` changed, deploy it separately and preserve the existing bot functionality.
- [ ] Update this README whenever triggers, limits, secrets, or processing behavior change.

# Science Channel — complete operating guide

This guide explains how to create an episode, edit its script, generate and upload images, render the video, and download or delete the result. The Science Channel uses four coordinated GitHub Actions workflows: the Gemini planner, Telegram image receiver, Telegram ZIP importer, and video renderer. All four operate on the `main` branch.

## Telegram + Cloudflare Worker connection

The Cloudflare Worker is the Telegram webhook and Stickman Lab control centre. It handles normal bot commands and GitHub controls. For image photos, image documents, ZIP files and `/episode YYYY-MM-DD/episode-NNN` selections, it forwards the Telegram update to GitHub using the `telegram_image_upload` repository_dispatch event. The existing Python receiver downloads the media from Telegram, validates it, writes the numbered images, and commits to `main`.

**Important:** do not run Telegram `getUpdates` polling or call `deleteWebhook` from the GitHub receiver. Telegram supports one update-delivery mode per bot token; the Worker webhook must remain registered.

The matching Worker source is [`cloudflare-worker.js`](../cloudflare-worker.js). After updating that source, deploy it to the existing Cloudflare Worker and visit its `/setup` endpoint once to register the webhook. Keep the existing Worker secrets and variables configured, including `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_WORKER_URL`, and `UPLOAD_LINK_SECRET`. The GitHub token must be allowed to create repository dispatch events and control the repository workflows.

## How the complete workflow operates

The Science Channel pipeline has four GitHub Actions workflows. The planner creates the episode package; either Telegram workflow can receive/import the 48 images; the renderer turns the completed package and images into a narrated video. Image generation and review remain a human-in-the-loop stage.

### The end-to-end process

```text
Daily schedule or manual start
            |
            v
1. GEMINI DAILY PLANNER
   Invents one new science topic
   Writes episode details and 48-scene narration
   Creates 48 matching image prompts
            |
            v
2. EPISODE PACKAGE IS COMMITTED TO GITHUB
   science-channel/daily-episodes/YYYY-MM-DD/episode-001/
   episode.json | script.md | scenes.json | image-prompts.md
   images/incoming/
            |
            v
3. YOU REVIEW / EDIT THE EPISODE
   Correct the title, narration, scenes and image prompts
   Keep all 48 scenes in the same order
            |
            v
4. YOU GENERATE, COMPRESS AND UPLOAD 48 IMAGES
   Prepare one optimized ZIP (target under 23 MiB) OR 48 separate files
   Upload into that episode's images/incoming/ folder
            |
            v
5. RENDER WORKFLOW STARTS
   Automatically after a real image/ZIP or READY commit (the `.gitkeep` placeholder is ignored),
   or manually when you provide the episode_path
            |
            v
6. VALIDATE AND RENDER
   Checks 48 scenes, narration sections and images
   Makes 16:9 visuals + Edge TTS narration
   Combines them into final-video.mp4 with word-aligned karaoke captions
            |
            v
7. OUTPUT ARTIFACT IS UPLOADED
   Topic-based artifact name; retained for 2 days
            |
            v
8. POST-RENDER TASKS
   Attempts Telegram video delivery (non-blocking)
   After successful Telegram delivery, removes uploaded ZIP/images and READY.txt from the Git repository
```

### How topic selection works

Every planner run randomly selects one broad science category, then asks Gemini to invent one fresh topic inside that category. The categories rotate across areas such as space and astronomy, the human body and mind, oceans and weather, animals, plants, everyday physics, light and sound, geology, technology and engineering, chemistry, fossils, and food science.

The planner reads `science-channel/topics.txt` **only as a style reference**. It does not choose episode topics from that file, work through its entries, or treat them as a topic queue. The examples demonstrate the intended tone: simple, specific, familiar, and naturally intriguing—for example, “Why do we get goosebumps?”, “How do bees communicate?”, or “Why is the sky blue?” Gemini must invent a different science question in that style.

For every run, the planner randomly selects one broad science category (such as space, the human body, oceans and weather, animals, plants, physics, light and sound, geology, technology, chemistry, fossils, or food science). Gemini is instructed to brainstorm at least 10 candidate ideas internally and choose the strongest new idea within that selected category. The goal is a question that makes a broad audience curious, has a satisfying evidence-based scientific answer, and offers enough layers and visuals for an 8–10 minute episode. Straightforward everyday science is welcome; exaggerated clickbait, manufactured disasters, bizarre body-horror, and unnecessarily complicated hypotheticals are discouraged.

The code also enforces the style-reference rule: if Gemini returns a title that exactly matches or closely rewords an entry in `topics.txt`, that candidate is rejected and the planner retries. It separately checks the complete generated-topic history and existing episode metadata, rejecting exact/title-similar repeats and using a semantic Gemini review to reject topics that cover the same underlying scientific subject even when phrased differently. The planner makes up to five topic-generation attempts; if it cannot find a sufficiently distinct topic, it stops rather than knowingly creating a duplicate.

To tune the writing style, edit the examples in `science-channel/topics.txt`; to change category choices, prompt rules, or the seed-reuse guard, edit `science-channel/scripts/gemini_planner.py`. Keep in mind that the seed entries are examples only, never a to-do list. Accepted topics are recorded in `science-channel/history/generated-topics.json`.

### Workflow A — Daily Gemini Planner

- **When it runs:** Automatically once every day at 01:15 UTC (06:45 India Standard Time). You can also manually run **Science Channel — Daily Gemini Planner** as often as you need; there is no one-episode-per-day cap.
- **What each run does:** Every automatic or manual run creates exactly one new episode. The planner randomly chooses a broad science category and asks Gemini to invent a fresh question in that category. `science-channel/topics.txt` is a style reference only; its titles are not selectable topics, and exact or closely reworded seed titles are rejected. It checks prior topics for duplicates, then writes the episode metadata and complete narration script and creates exactly 48 numbered scene records. Multiple manual runs on the same date create `episode-001`, `episode-002`, `episode-003`, and so on; earlier episodes are not overwritten.
- **Image prompts:** A second Gemini request creates exactly one visual prompt for each finalized scene. New prompts are told not to add a presenter or talking-head explainer by default; the image should depict the science concept, action, environment or visual metaphor in that scene.
- **What gets saved:** The planner creates the episode folder and its five starter items: `episode.json`, `script.md`, `scenes.json`, `image-prompts.md`, and `images/incoming/.gitkeep`. It also updates the topic history so the topic is not selected again.
- **How it finishes:** The workflow optionally sends `image-prompts.md` to Telegram, then commits the generated Science Channel package to the repository. Telegram is non-blocking: a missing Telegram secret or a send failure does not prevent the episode package commit.
- **What it does not do:** The planner does not generate the 48 image files and does not render the MP4. You generate the images and upload them before rendering.

### Workflow B — Telegram Image Receiver

File: `.github/workflows/telegram-image-receiver.yml`

- **Trigger:** the Cloudflare Worker receives Telegram webhook updates and forwards image/ZIP uploads and `/episode` selections through `repository_dispatch`. Manual workflow dispatch remains available for maintenance.
- **Branch:** checks out and commits only to `main`; it does not read or write `adaptive-cinematic-effects`.
- **Episode selection:** automatically selects the newest episode package on `main`. Send `/episode YYYY-MM-DD/episode-001` to choose another existing episode.
- **Uploads:** accepts individual JPG/JPEG, PNG or WebP images, or one ZIP containing exactly 48 supported images. Individual images are placed into the next missing scene number. A ZIP is expanded into 48 numbered scene files.
- **Completion:** when all 48 scene slots are present, the bot creates `READY.txt`. The workflow commits the images and receiver state to `main`; the image commit triggers the render workflow.
- **Chat restriction:** only messages from the configured `TELEGRAM_CHAT_ID` are processed. `/start` and `/help` display bot instructions.

### Workflow C — Telegram ZIP Import

File: `.github/workflows/telegram-zip-import.yml`

This is an alternative to sending the ZIP directly to the bot. First upload any `.zip` file directly into `science-channel/telegram-uploads/` on `main`. Then open Actions → **Telegram ZIP Import** → Run workflow and provide both required inputs:

- `episode_path`: the exact episode folder, for example `science-channel/daily-episodes/2026-11-01/episode-001`.
- `zip_path`: the full staged ZIP path, for example `science-channel/telegram-uploads/dream.zip`.

The filename does not need to follow a special naming pattern, but the file must end in `.zip` and be directly inside `science-channel/telegram-uploads/`. The importer checks that the archive is valid and contains exactly 48 supported images, rejects unsafe paths and oversized files, extracts the images into the episode's `images/incoming/` folder, creates `READY.txt`, commits the images to `main`, and removes the staged ZIP. That commit starts the renderer.

This workflow uses the `GH_PAT` repository secret to push imported files. Configure it as a personal access token with repository contents write permission. Do not put the token in a workflow input or source file.

### The manual creative stage — your review and images

After the planner finishes, you control the episode before it becomes a video. You can edit the title, narration, scene descriptions and image prompts in the episode folder. Generate one image for each final scene prompt, then upload the 48 images into that same episode's `images/incoming/` directory. The renderer does not generate images for you.

If you revise narration after generating images, revise the matching prompt and replace the image too. This keeps what viewers see aligned with what they hear.

### Workflow B — Free Science Visuals Renderer

- **How it starts:** It can run from a push that adds real files to an episode's `images/incoming/` folder (the `.gitkeep` placeholder alone is ignored) or changes its `READY.txt` marker, or you can start **Free Science Visuals — Render Ready Episode** manually in Actions.
- **Choosing the episode:** For a manual run, enter the exact folder in the optional `episode_path` field. If left blank, it chooses the newest episode it finds with a READY marker or incoming image files. For a push run, the changed files must identify exactly one episode; commits affecting multiple episodes are rejected.
- **Validation:** It checks the episode metadata and scene data, requires exactly 48 ordered scene records, checks for 48 numbered narration sections in `script.md`, and requires exactly 48 supported images (either one ZIP or individual files, not a mixture).
- **Rendering:** It converts the images into 16:9 frames, creates spoken narration using Edge TTS and the configured voice, and combines the visuals and narration into `output/final-video.mp4`. **It uses faster-whisper Small on CPU to align narration word-by-word, then burns phrase-based karaoke captions into the video. The active word is yellow; surrounding words are white with a dark outline.**
- **Artifact upload:** after rendering, it uploads the final MP4 only as a topic-named GitHub Actions artifact. The artifact is retained for **2 days**.
- **Telegram delivery:** the workflow attempts to send the MP4 to the configured Telegram chat. This step is non-blocking, so a Telegram failure does not erase an artifact that has already been uploaded.
- **Cleanup after successful delivery:** only when Telegram reports success, the workflow deletes every uploaded file in the episode's `images/incoming/` folder except `.gitkeep`, and removes `READY.txt`. It commits the cleanup to `main`. This removes both ZIP archives and individual scene images, and allows the same ZIP filename to be uploaded again after the cleanup commit reaches `main`.
- **If Telegram delivery fails:** cleanup is skipped. The ZIP/images and READY marker remain in the repository so you can retry delivery/rendering. The MP4 artifact may still be available because artifact upload occurs before Telegram delivery.

### What happens if a step fails?

- If the planner fails before committing, a new complete episode package may not be available. Check the planner run's logs in Actions.
- If you have not uploaded all 48 images, or the script/scenes do not pass validation, rendering stops and the rendered artifact is not uploaded.
- If rendering or artifact-name generation fails before the upload step, there is no rendered-video artifact from that run.
- If artifact upload succeeds and Telegram delivery fails, the workflow continues but skips cleanup; the artifact remains available until manually deleted or its 2-day retention expires. If the cleanup commit itself cannot be pushed, the run fails after artifact upload and Telegram delivery, and the uploaded source files may remain in the repository.
- The planner's episode files and uploaded individual images are repository files. The rendered artifact is a separate downloadable item under the Actions run; it is not automatically committed as a video file in the episode folder.

## Quick workflow

1. Run the **Science Channel — Daily Gemini Planner** workflow (or wait for its daily schedule).
2. Open the new episode folder under `science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`.
3. Review or edit `script.md`, `scenes.json`, `episode.json`, and `image-prompts.md`.
4. Generate exactly 48 images from the image prompts.
5. Run `science-channel/scripts/prepare_images.py` to resize/compress the images into one ZIP targeting under 23 MiB, or use Git command line for larger files.
6. Upload that ZIP (or 48 individual images) into that episode's `images/incoming/` folder, or use one of the Telegram upload workflows described above.
7. For direct repository uploads, add an empty `READY.txt` file in the episode folder and commit the images and marker. Alternatively, run the render workflow manually and enter the episode folder path.
8. Open the render workflow run, download the MP4 artifact, and save it.

## 1. Create a new episode

The planner runs automatically once every day at **01:15 UTC (06:45 India Standard Time)**. This is the automatic schedule, not a daily production limit. **Every manual run also creates one new episode**, and you may manually run it multiple times on the same day. The planner assigns the next available episode number for that date, so it does not overwrite earlier episodes. You can start it manually:

1. Open the repository's **Actions** tab.
2. Select **Science Channel — Daily Gemini Planner**.
3. Click **Run workflow**, select the `main` branch, and start it.
4. Wait for the run to finish. Open the commit or browse to `science-channel/daily-episodes/` to find the new episode.

The folder format is:

```text
science-channel/
└── daily-episodes/
    └── YYYY-MM-DD/
        └── episode-001/
            ├── episode.json
            ├── script.md
            ├── scenes.json
            ├── image-prompts.md
            └── images/
                └── incoming/
```

If more than one episode is created on the same date, the planner uses the next available number (for example, `episode-002`) rather than overwriting an earlier folder.

The planner requires the GitHub Actions secret `GEMINI_API_KEY`. The optional repository variable `SCIENCE_GEMINI_MODEL` overrides the model in `science-channel/settings.json`.

Telegram delivery of `image-prompts.md` is optional. It uses `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; missing secrets or a Telegram delivery failure do not prevent the episode package from being committed.

## 2. Understand and manually edit the episode files

Open the episode folder in GitHub and click a file to view it. To edit, click the pencil icon, make your changes, then click **Commit changes**.

| File | Purpose | What you may edit |
|---|---|---|
| `episode.json` | Episode metadata | Title, description, date and other episode details. Keep `scene_count` at 48. |
| `script.md` | Spoken narration | Edit the title, description and narration under each `## Scene 01` through `## Scene 48` heading. |
| `scenes.json` | Structured scene plan | Keep exactly 48 objects numbered consecutively from 1 to 48. Update narration and visual beats to match your script. |
| `image-prompts.md` | Image-generation instructions | Edit each scene's prompt so the image matches the final narration and visual beat. |
| `images/incoming/` | Input images | Upload the 48 finished scene images here. |

### Script-editing rules

- Keep all 48 scene headings in `script.md`, numbered in order from 01 to 48. Do not remove or duplicate a scene.
- Put only the words to be narrated under each scene heading. The renderer reads the narration from `script.md`.
- Keep `scenes.json` at exactly 48 ordered scene records. If you change a scene's narration or visual idea, update its matching record too.
- If you change the script after images have already been generated, also revise the corresponding image prompt and replace that scene's image. Otherwise the narration and visuals may no longer match.
- Editing the script or prompts alone does **not** render a video. Upload the finished images and start the render workflow after your edits.

### Image style: no default presenter

New Gemini-generated image prompts are instructed **not** to add a presenter, host, teacher, narrator, talking-head character, or recurring man by default. Images should show the actual scientific subject, action, environment, objects, or visual metaphor for that scene. They request a **1920×1080 landscape (16:9) composition**, with **WebP preferred** when the image tool supports it because it usually offers an excellent quality-to-size balance. PNG, JPG/JPEG, BMP, GIF, TIF and TIFF are also accepted by the renderer. JPG is not required. The prompt now states explicitly: **target 500 KB–2 MB per image** and use available quality/compression controls to aim for that range, but never visibly degrade the image just to meet it. This is guidance, not a hard limit.

A human figure may appear when the scene itself calls for one, but should be part of the scene rather than standing in front of the viewer and explaining it. For example, a dream-flying scene should show a person soaring through dreamlike clouds and skies, not a man presenting an explanation.

This prompt rule applies to **newly generated episodes**. Existing episode prompt files are not rewritten automatically. Edit an older `image-prompts.md` yourself if you want to apply the new visual direction to that episode.

## 3. Generate and prepare the 48 images

Open that episode's `image-prompts.md`. It contains one prompt for each numbered scene. Generate one image for each prompt, keeping the scene numbers clear.

The prompts request a **1920×1080 landscape (16:9) composition**, preferring **WebP** when available for its quality-to-size balance. The renderer accepts PNG, JPG/JPEG, WebP, BMP, GIF, TIF and TIFF; JPG is not mandatory. The suggested **500 KB–2 MB per image** is only a practical target. You can upload supported images directly, or optionally run the local preparation utility to resize/convert them into numbered JPGs and create a ZIP targeting under **23 MiB**, leaving room below GitHub's 25 MB browser-upload limit.

### Prepare a browser-upload-friendly ZIP

1. Download the 48 generated images into one local folder. Keep filenames numbered by scene if possible (for example, `scene-001.png` through `scene-048.png`).
2. Install Python 3 and Pillow once:
   `python -m pip install Pillow`
3. From the repository root, run:

   ```bash
   python science-channel/scripts/prepare_images.py "/path/to/48-original-images" "science-channel-images.zip"
   ```

   On Windows, use a folder path such as `"C:\Users\YourName\Pictures\science-images"`.
4. The script checks for exactly 48 supported images, orders them by scene number when possible, converts them to 1920×1080 JPGs, and creates one ZIP with filenames `scene-001.jpg` through `scene-048.jpg`.
5. Check the printed ZIP size. The default target is 23 MiB. If it reports that the ZIP is still larger, use Git command line or run it again with a lower target, for example `--max-mb 20`.
6. Upload the resulting ZIP to that episode's `images/incoming/` folder.

The utility creates the ZIP locally; it does not upload files to GitHub automatically. The renderer still validates the 48 images and creates its own 1280×720 working frames for the video.

Recommended filenames:

```text
scene-001.png
scene-002.png
scene-003.png
...
scene-048.png
```

Use the same numbering for JPG, JPEG or WebP files if you prefer those formats. Clear scene numbering helps the renderer match each image to the right narration scene.

Supported image formats: **PNG, JPG, JPEG, WebP, BMP, GIF, TIF and TIFF**.

## 4. Upload images to the correct folder

Upload images only into the current episode's:

```text
science-channel/daily-episodes/YYYY-MM-DD/episode-001/images/incoming/
```

Replace the date and episode number with the folder you are working on. Do not upload images into the general `daily-episodes` folder, another date's folder, or `output/`.

You can upload in either of these ways:

**Option A — one ZIP (usually easiest)**

1. Put exactly 48 supported image files in one ZIP archive.
2. Keep the scene numbers in the filenames, such as `scene-001.png` through `scene-048.png`.
3. Upload that single ZIP into `images/incoming/`.

**Option B — 48 individual files**

1. Upload exactly 48 supported image files directly into `images/incoming/`.
2. Use numbered filenames so the order is clear.

Important:
- Upload either **one ZIP** or **48 individual images** in an episode's incoming folder. Do not mix ZIPs and individual images.
- A ZIP must contain exactly 48 supported image files. Avoid duplicate filenames inside the ZIP.
- Do not upload multiple ZIP archives for one episode.
- The renderer first uses a complete, unique scene-number sequence (for example, `scene-001.png`). If it cannot find one, it sorts filenames naturally (`image2` before `image10`).
- The renderer converts the source images into 16:9 video frames.

### Upload using the GitHub website

1. Browse to the episode's `images/incoming/` folder.
2. Click **Add file → Upload files**.
3. Drag in the ZIP or select the 48 images.
4. Click **Commit changes**.

## 5. Start video rendering

### Automatic rendering

For automatic rendering, add an empty file named exactly `READY.txt` in the episode folder (beside `episode.json`), then commit it together with the image upload whenever possible.

The render workflow also watches real uploaded files under `images/incoming/`; the planner's `.gitkeep` folder placeholder does not trigger rendering by itself. It validates the selected episode and will fail if the image count or script structure is incomplete. Upload images for **one episode per commit**: a push that changes more than one episode is rejected to prevent rendering the wrong one.

### Manual rendering (choose the exact episode)

1. Open the repository's **Actions** tab.
2. Select **Free Science Visuals — Render Ready Episode**.
3. Click **Run workflow** and choose the `main` branch.
4. In the optional `episode_path` field, enter the full folder path, for example:

   `science-channel/daily-episodes/2026-10-31/episode-001`

5. Click **Run workflow**.

Entering the exact path is recommended when you have multiple episode folders. If you leave it blank, the workflow selects the newest episode it finds with a `READY.txt` marker or uploaded incoming image files.

The renderer checks that there are 48 ordered scene records in `scenes.json`, 48 corresponding scene sections with narration in `script.md`, and exactly 48 input images. It generates narration using Edge TTS and renders the video.

**Karaoke captions are generated from the final Edge-TTS audio using faster-whisper Small. Each short phrase stays visible while the current spoken word is highlighted yellow; other words remain white with a dark outline.**

## 6. Find and download the rendered video

1. Open **Actions** and select the completed **Free Science Visuals — Render Ready Episode** run.
2. Scroll to the **Artifacts** section near the bottom of the run page.
3. Click the artifact named from the episode topic (it starts with `science-channel-`) to download it.
4. Unzip the downloaded artifact. The final video is `final-video.mp4` inside the episode's `output/` contents. Other supporting render files may also be included.

Artifacts are retained for **2 days**. Download the video before the retention period expires. You can delete an artifact earlier from the workflow run's Artifacts section using its delete/trash control.

The artifact upload happens before Telegram delivery and ZIP cleanup. Therefore, if a later Telegram or ZIP-cleanup step fails, an artifact that was already uploaded remains available until it expires or is manually deleted. If rendering or artifact creation fails before the upload step, no rendered-video artifact is created.

## 7. ZIP cleanup and repository files

After the artifact upload and **only if Telegram delivery succeeds**, the render workflow deletes all uploaded files directly inside the repository's `images/incoming/` folder (ZIP archives and individual scene images), preserves `.gitkeep`, removes `READY.txt`, and pushes the cleanup commit to `main`. This permits reuse of the same ZIP filename after the cleanup commit has completed. If Telegram delivery fails, cleanup is skipped and the uploaded files remain available for retry. If the cleanup push fails, the artifact may already be available even though the overall workflow run reports failure.

## 8. GitHub Actions settings required

In **Settings → Secrets and variables → Actions**:

- Add repository secret `GEMINI_API_KEY` for the planner.
- Optionally add repository variable `SCIENCE_GEMINI_MODEL` to choose the Gemini model.
- Optionally add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets if you want Telegram delivery.

The render workflow installs FFmpeg, DejaVu fonts, Edge TTS and faster-whisper itself; no extra repository dependency setup is required.

## 9. What this pipeline changes

Science Channel code, settings, topics, history and episode files are kept under `science-channel/`. The complete workflow set is:

- `.github/workflows/science-channel-daily-planner.yml` — creates the episode package and prompts.
- `.github/workflows/telegram-image-receiver.yml` — receives upload events forwarded by the Cloudflare Worker and commits uploaded images to `main`.
- `.github/workflows/telegram-zip-import.yml` — manually imports a staged ZIP from `science-channel/telegram-uploads/`.
- `.github/workflows/free-science-visuals.yml` — validates, renders, uploads the MP4 artifact, sends it to Telegram and cleans source uploads after successful delivery.

All four Science Channel workflows use `main`. The separate `.github/workflows/ai-video-test.yml` is a legacy root-level AI Video Experiment and is not part of the episode pipeline. Unrelated root-level generator scripts, topics, history and configuration are outside the Science Channel pipeline's scope.


## Customize the Science Channel

This section explains which settings are safe to change, where to change them, and which changes require coordinated code updates. Make changes on **main**. In GitHub, open a file, select the pencil icon, edit it, and commit. For larger changes, clone the repository, edit locally, run checks, then push or open a pull request.

### 1. Settings you can change in one place

File: `science-channel/settings.json`

| Setting | Current value | What it controls | Change guidance |
|---|---:|---|---|
| `scene_count` | 48 | Number of narration scenes | Keep at 48 unless all planner, receiver, importer and renderer assumptions are updated together. |
| `target_minutes_min` / `target_minutes_max` | 8 / 10 | Planner's target episode duration | You may adjust the target, but also review the narration prompt in `gemini_planner.py`. |
| `language` | English | Intended episode language | Change only together with the planner prompt and a voice that supports the language. |
| `aspect_ratio` | 16:9 | Intended image/video shape | Renderer currently normalizes images to 1280×720 before producing the configured output dimensions. |
| `width` / `height` | 1920 / 1080 | Final video resolution | Keep a 16:9 pair unless you also update image prompts and rendering/caption layout. |
| `fps` | 30 | Final frame rate | Higher values increase render time and file size. |
| `gemini_model` | gemini-3.5-flash-lite | Planner text model | Must be a model available to your Gemini API key. Workflow variable `SCIENCE_GEMINI_MODEL` overrides this value. |
| `voice` | en-US-AndrewMultilingualNeural | Edge TTS voice | Use a valid Edge TTS voice name that supports the episode language. |
| `speech_rate` | +0% | Narration speed | Example adjustments: `-5%` slower or `+5%` faster. Listen to a test render. |
| `required_uploaded_images` | 48 | Expected image count documentation/config | Keep aligned with all code; do not change alone. |
| `uploaded_image_folder` | images/incoming | Input folder name | Changing it requires updating workflows and scripts too. |

Example voice/speed edit:

```json
{
  "voice": "en-US-EmmaMultilingualNeural",
  "speech_rate": "-5%"
}
```

Keep the JSON valid: use double quotes, commas between properties, and no trailing comma. The renderer reads voice, speech_rate, width, height and fps from this settings file. A new voice or speed affects the next render; it does not change an MP4 that has already been created.

### 2. Change the Gemini model

There are two ways:

1. Edit `gemini_model` in `science-channel/settings.json`.
2. Or, preferably for workflow-only overrides, open repository Settings → Secrets and variables → Actions → Variables and set `SCIENCE_GEMINI_MODEL`.

The planner workflow passes that variable as `GEMINI_MODEL`; if it is empty, the planner uses `settings.json`. The current planner calls the Gemini `generateContent` API and expects JSON output. Choose a model that supports the API and structured JSON generation. A different provider is not a drop-in replacement: the API client, authentication and response parsing in `gemini_planner.py` would need to be adapted.

### 3. Change topic ideas and topic-generation behavior

**Add seed topics:** edit `science-channel/topics.txt`. Put one topic idea on each line. Keep ideas broad, understandable and curiosity-driven. The planner uses this file as inspiration alongside its randomly selected category; it is not a strict queue of topics.

**Change categories and examples:** edit the `topic_pillars` list in `science-channel/scripts/gemini_planner.py`. Each entry contains a category and a sample question. The planner randomly selects one category for each run.

**Change title quality, audience or narration rules:** in the same Python file, edit the prompt text inside the topic-generation and episode-generation requests. You can adjust:
- target audience and reading level;
- curiosity gap and title style;
- acceptable subject areas and subjects to avoid;
- narration tone, factual caution and scene pacing;
- visual prompt style and the no-presenter preference.

Do not remove the semantic duplicate-review step or its historical episode list. The planner checks exact/near-identical titles and asks Gemini to compare the underlying subject against the full history. It fails closed if the duplicate reviewer cannot return a reliable boolean decision. This is a strong safeguard, not a mathematical guarantee that no related topic can ever recur.

**Topic history:** `science-channel/history/generated-topics.json` stores titles and, where available, topic angles and categories. The planner also scans existing episode metadata. Do not casually delete or reset this file; doing so weakens repeat protection. If you intentionally reset history, understand that older episode subjects may be selected again.

### 4. Change an individual episode without changing the generator

Open the episode folder under `science-channel/daily-episodes/YYYY-MM-DD/episode-NNN-topic/`.

| File | Safe edits | Keep in sync |
|---|---|---|
| `episode.json` | Title, description and metadata | Keep `scene_count` at 48. |
| `script.md` | Spoken narration under Scene 01–48 | Keep every heading, order and non-empty narration. |
| `scenes.json` | Scene titles, visual descriptions and narration metadata | Exactly 48 ordered scene records numbered 1–48. |
| `image-prompts.md` | Image-generation prompts | One prompt per scene, matching the final narration and visual. |

If you change a scene's narration, update its matching scenes.json entry and image prompt, then regenerate that image. If you change the episode title, update the metadata consistently before rendering because the title is used for the artifact and MP4 filename. Editing an episode does not automatically regenerate its images or video.

### 5. Change the karaoke captions

File: `science-channel/scripts/karaoke_subtitles.py`.

The caption style is defined in the ASS `Style:` line inside `generate_karaoke_ass()`. Current behavior:
- faster-whisper Small runs on CPU and creates word timestamps;
- words are grouped into phrases of up to 7 words, with sentence punctuation also ending a phrase;
- the current spoken word is highlighted yellow; other words are white;
- DejaVu Sans is bold, with a dark outline and shadow;
- captions are horizontally centered near the bottom of the frame.

You can change the font name, font size multiplier, primary/highlight colors, outline width, shadow and vertical margin in the ASS style. Change `make_groups(words, max_words=7)` to alter phrase length. Keep ASS color values in ASS format (not ordinary HTML hex). Test a short render after changing subtitle code. The renderer installs DejaVu fonts and faster-whisper as part of the workflow.

### 6. Change image requirements or upload behavior

**Image-generation instructions:** edit the prompt-building logic in `science-channel/scripts/gemini_planner.py`. The prompts currently request landscape 16:9 images, prefer WebP when supported by the image tool, and describe a practical file-size target. The actual renderer accepts PNG, JPG/JPEG, WebP, BMP, GIF, TIF and TIFF.

**Telegram Image Receiver:** edit `science-channel/scripts/telegram_image_receiver.py` to change accepted Telegram formats, individual-image size checks, ZIP image checks, episode auto-selection or bot replies. It currently accepts JPG/JPEG, PNG and WebP; limits each image to 20 MiB; and expects exactly 48 images in a ZIP. It receives update JSON forwarded by the Cloudflare Worker; it must not call `getUpdates` or `deleteWebhook` while the Worker webhook is active.

**ZIP Import:** edit `science-channel/scripts/import_telegram_zip.py` to change staging validation. The current importer accepts any filename ending in `.zip` directly inside `science-channel/telegram-uploads/`, requires exactly 48 supported images, limits the ZIP to 25 MiB and each image to 20 MiB, rejects unsafe archive paths/symlinks and duplicate basenames, and refuses to overwrite existing incoming images.

**Image preparation:** `science-channel/scripts/prepare_images.py` converts exactly 48 source images to numbered 1920×1080 JPGs and creates a ZIP. Default target is 23 MiB; use `--max-mb 20` for a smaller target. It requires Pillow:

```bash
python -m pip install Pillow
python science-channel/scripts/prepare_images.py "/path/to/48-images" "science-channel-images.zip"
```

Do not mix ZIP and individual image files in one episode's incoming folder. Direct renderer uploads accept the broader set of image formats listed above, but the Telegram receiver/importer intentionally support a smaller set.

### 7. Change workflow schedules, triggers and artifact retention

Workflow files are under `.github/workflows/`.

| Workflow file | Current schedule/trigger | Important settings |
|---|---|---|
| `science-channel-daily-planner.yml` | Daily at 01:15 UTC; manual dispatch | 60-minute timeout, main branch, Gemini and optional Telegram secrets. |
| `telegram-image-receiver.yml` | Cloudflare webhook repository_dispatch; manual maintenance dispatch | 8-minute timeout, main branch, Telegram bot secrets. |
| `telegram-zip-import.yml` | Manual dispatch only | Requires `episode_path` and `zip_path`; uses GH_PAT. |
| `free-science-visuals.yml` | Push of incoming files/READY.txt on main; manual dispatch | 90-minute timeout; final MP4 artifact retention is 2 days. |
| `ai-video-test.yml` | Daily at 05:30 UTC; manual dispatch | Separate root pipeline; artifact retention is 7 days. |

To change a cron schedule, edit the `cron:` expression in the matching YAML file. Cron uses UTC. For example:
- `15 1 * * *` = 01:15 UTC every day = 06:45 IST.
- `*/10 * * * *` = every 10 minutes.
- `30 5 * * *` = 05:30 UTC every day = 11:00 IST.

Change artifact retention by editing `retention-days` in the relevant `actions/upload-artifact` step. GitHub repository/plan limits still apply. Keep the renderer's push path filters and main-only checkout intact. The planner and receiver share a concurrency group so writes to main are serialized.

### 8. Required secrets and variables

Repository → Settings → Secrets and variables → Actions:

| Name | Type | Used by | How to obtain/use |
|---|---|---|---|
| `GEMINI_API_KEY` | Secret | Science planner and legacy AI experiment | Create an API key in Google AI Studio; never commit it. |
| `SCIENCE_GEMINI_MODEL` | Variable (optional) | Science planner | Model override; takes precedence over settings.json. |
| `TELEGRAM_BOT_TOKEN` | Secret | Planner prompt send, image receiver and render video send | Create a bot with Telegram's BotFather; store its token as a secret. |
| `TELEGRAM_CHAT_ID` | Secret | Telegram workflows | The chat/group ID authorized for receiving and sending bot messages. |
| `GH_PAT` | Secret | Telegram ZIP Import | Personal access token with repository contents write access. |
| `CF_ACCOUNT_ID` | Secret | Legacy AI Video Experiment | Cloudflare account identifier. |
| `CF_API_TOKEN` | Secret | Legacy AI Video Experiment | Cloudflare API token authorized for Workers AI. |

After changing a secret, rerun the relevant workflow. Do not put tokens in YAML, Python, README, issue comments or workflow inputs. If a token is exposed, revoke it and create a replacement.

### 9. What NOT to change casually

- Do not change the Science Channel scene count from 48 in just one file. Planner, receiver, importer, READY detection, image prompts and renderer must agree.
- Do not change the Science Channel folder paths without updating workflow path filters and Python paths.
- Do not change Science Channel workflows to check out or push to `adaptive-cinematic-effects`; the required branch is `main`.
- Do not delete topic history unless you intentionally want to allow old topics to be proposed again.
- Do not remove the planner/receiver concurrency group or fetch/rebase/push protections without considering simultaneous scheduled and manual runs.
- Do not assume that changing the Gemini model ID switches to another LLM provider. Different providers often need different API clients and response parsing.
- Do not change a workflow's artifact retention and assume the artifact is permanent; download important videos locally.

### 10. Test changes before relying on automation

1. Validate JSON files after editing settings or episode metadata.
2. Validate YAML indentation after editing workflows.
3. Run the relevant Python script locally where practical, with secrets supplied through environment variables rather than hardcoded.
4. For caption or rendering changes, use a test episode and inspect the MP4 before changing production settings.
5. For workflow changes, use **Actions → workflow → Run workflow** on `main` when safe.
6. Check the complete Actions log, downloaded artifact, Telegram delivery and cleanup commit. A successful code commit is not proof of an end-to-end successful workflow run.



---

# 📲 Telegram operations — detailed Science Channel manual

This section is specifically for the 48-scene Science Channel pipeline. For the separate Cloudflare AI Video Experiment's Telegram delivery, see [AI Video Experiment — Telegram and Cloudflare details](../AI_README.md#-telegram--complete-bot-setup-upload-delivery-and-modification-guide).

## 1. What Telegram does in this pipeline

Telegram is the transport layer between the episode package and the render workflow. It does not generate the scene images.

| Telegram operation | Trigger/workflow | File or result |
|---|---|---|
| Send the 48 image prompts | Planner workflow, after episode commit | Sends `image-prompts.md` as a document |
| Receive 48 individual images or one ZIP | Cloudflare Worker webhook → Telegram Image Receiver | Saves numbered files in the selected episode's `images/incoming/` |
| Import a ZIP staged in GitHub | Telegram ZIP Import, manual workflow | Extracts 48 images into `images/incoming/` |
| Send finished episode | Render workflow, after MP4 artifact upload | Sends the final MP4 to the configured chat |
| Cleanup source images | Render workflow, only after successful Telegram send | Deletes incoming images/ZIP and READY marker from main |

The Worker webhook forwards direct Telegram uploads to the receiver; the ZIP importer remains a separate repository-staging upload route. Choose one route for an episode; do not upload the same 48 images through both routes.

## 1A. How the existing bot is implemented (code-level map)

This repository does not run a separate always-on Telegram server. The Science Channel bot uses a Cloudflare Worker Telegram webhook that forwards image-upload updates to a Python receiver executed by GitHub Actions.

```text
Telegram Bot API
  └─ Cloudflare Worker webhook
       ├─ handles control commands and GitHub operations
       └─ forwards photo/document/ZIP and /episode updates
            └─ .github/workflows/telegram-image-receiver.yml (repository_dispatch)
                 └─ science-channel/scripts/telegram_image_receiver.py
                      ├─ read TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
                      ├─ load telegram-bot-state.json (selected episode)
                      ├─ check message.chat.id against configured chat ID
                 ├─ handle /start, /help, /episode
                 ├─ getFile and download photo/document
                 ├─ store scene-01 ... scene-48
                 ├─ create READY.txt when all 48 slots exist
                 └─ save updated state
                      └─ GitHub Actions commits files and state to main
                           └─ push starts free-science-visuals.yml
```

### Python receiver internals

| Function/constant | What it does now | Where to modify |
|---|---|---|
| `TOKEN`, `CHAT_ID`, `API` | Read token/chat ID from environment and construct Bot API base URL | Change credential names only together with workflow secret mapping |
| `api(method, **kwargs)` | Calls Telegram Bot API with `requests.post`, checks HTTP and Telegram `ok` response | Change HTTP timeout, request handling or API error logging |
| `send(text)` | Sends a Telegram `sendMessage` reply to configured chat | Change bot reply delivery or default reply formatting |
| `load_state()`, `save_state()` | Read/write the selected episode path in receiver state | Change persistence carefully; Telegram delivery is managed by the Worker webhook |
| `valid_episode()` | Validates date/episode path and requires `episode.json` | Change accepted episode naming/path only with planner and renderer |
| `newest_episode()` | Finds latest episode folder containing `episode.json` | Change automatic episode selection |
| `image_payload()` | Detects Telegram photos, supported image documents and ZIP documents | Change accepted file formats/MIME rules |
| `scene_numbers()` | Finds already received scene numbers 01–48 | Change naming/count only with the rest of the 48-scene pipeline |
| `main()` | Processes one Worker-forwarded update, filters chat, handles episode selection, downloads files, writes images and READY marker | Change upload/selection behavior |

### Workflow internals

`.github/workflows/telegram-image-receiver.yml` is triggered by the Cloudflare Worker through the `telegram_image_upload` repository_dispatch event and also supports manual maintenance runs. It checks out `main`, installs Python 3.11 and `requests`, maps the Telegram secrets and forwarded update JSON into environment variables, runs the receiver, then commits changed episode files and `science-channel/telegram-bot-state.json` to `main`. It shares the `science-channel-main-writer` concurrency group with the planner so the two main-branch writers do not race each other.

### How the outgoing messages are sent

- **Planner prompt document:** `.github/workflows/science-channel-daily-planner.yml` uses a direct Telegram Bot API `sendDocument` request with multipart fields for chat ID, `image-prompts.md` and caption.
- **Finished MP4:** `.github/workflows/free-science-visuals.yml` uses `PonomarevDA/telegram-upload@v1` with the bot token, chat ID, MP4 path and message caption.
- **Staged ZIP import:** `.github/workflows/telegram-zip-import.yml` is a separate manual GitHub workflow; it does not receive a ZIP through Telegram. It extracts a ZIP already committed under `science-channel/telegram-uploads/` and uses `GH_PAT` to push the result to `main`.

### Safely customize it

- To change bot token or chat, replace `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in GitHub Secrets. Do not hardcode them.
- To change bot replies or add a command, edit `main()` and `send()` in `science-channel/scripts/telegram_image_receiver.py`. Handle the command before file processing and use `continue` after replying.
- Telegram intake is webhook-triggered. Do not add a `getUpdates` schedule or call `deleteWebhook`; keep `repository_dispatch` and `workflow_dispatch` enabled.
- To change upload formats/limits, update `image_payload()`, ZIP suffix checks and the size guards together. Also update this README and the AI README's Telegram manual.
- To change outgoing captions, edit the `sendDocument` caption in the planner workflow or the upload action's `message` in the renderer workflow.
- To change the number of images, update every component that assumes 48 scenes: planner, receiver, ZIP importer, episode settings, renderer, validation, prompts and documentation. A partial change will break the upload-to-render handoff.
- Keep receiver checkout, commit and push targets on `main`. Do not redirect Science Channel Telegram automation to `adaptive-cinematic-effects`.

## 2. Bot setup and GitHub configuration

Create a bot using Telegram's official **@BotFather**:

1. Open BotFather in Telegram and send `/newbot`.
2. Choose the bot display name and a unique username ending in `bot`.
3. Save the API token privately.
4. Open your new bot and press Start.
5. Send a message to the bot so Telegram has an update containing your chat ID.
6. Use the configured numeric `TELEGRAM_CHAT_ID` from the existing bot setup. Do not call `getUpdates` while the Worker webhook is registered. Treat the bot token as a password; do not paste tokenized URLs into public places.
7. In GitHub, open repository **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret | Value | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather token | Authenticates Bot API calls and video-upload action |
| `TELEGRAM_CHAT_ID` | Numeric private chat or group ID | Destination for outgoing messages and allowlisted source chat for incoming uploads |
| `GH_PAT` | Personal access token with repository contents write access | Allows the ZIP importer to push extracted files to main |

The receiver checks the incoming chat ID for exact equality with `TELEGRAM_CHAT_ID`. Group IDs may be negative; keep the minus sign. A private chat with the bot is simplest. If you use a group, add the bot and ensure group privacy settings allow it to receive the image/document messages you intend to send.

Never add tokens to the repository, README, source code, workflow inputs or episode files. If a token leaks, revoke it and replace the matching GitHub secret.

## 3. Telegram Image Receiver — Worker webhook intake

Workflow: [telegram-image-receiver.yml](../.github/workflows/telegram-image-receiver.yml)

- Trigger: Cloudflare Worker sends a `telegram_image_upload` repository_dispatch event for each image/ZIP upload or `/episode` selection.
- Manual run: GitHub Actions → Telegram Image Receiver → Run workflow (maintenance only; it has no Telegram update to process).
- Runtime: Ubuntu latest, Python 3.11, `requests`, 8-minute job timeout.
- Permissions: repository contents write.
- Branch: always checks out and pushes to `main`.
- State file: `science-channel/telegram-bot-state.json`.
- Receiver script: `science-channel/scripts/telegram_image_receiver.py`.

The Cloudflare Worker is the always-available Telegram webhook. GitHub Actions starts the receiver when the Worker forwards a relevant update; the receiver downloads and processes that specific Telegram message. The receiver must never call `getUpdates` or `deleteWebhook`, because that would compete with or remove the Worker webhook.

The state file stores the selected episode path. Telegram update delivery and duplicate webhook retries are handled at the Worker/GitHub event layer; do not delete or reset the selected episode without intending to change the current upload destination.

### Commands

| Command | Result |
|---|---|
| `/start` | Displays the bot's upload instructions. |
| `/help` | Displays the same upload instructions. |
| `/episode YYYY-MM-DD/episode-NNN` | Selects an existing episode already committed to main. |

Example:

```text
/episode 2026-11-01/episode-001
```

The date and episode folder must match the actual repository path, and `episode.json` must exist on main. The bot does not create an episode from this command.

If no valid episode is selected, the receiver chooses the newest episode package on main. Its auto-selection logic can replace an older selected episode when a newer package appears. Check the bot's selection confirmation before uploading images to an older episode.

### Upload individual images

Accepted formats are JPG/JPEG, PNG and WebP. Telegram photo messages are saved as JPG. Documents are accepted when their extension/MIME type identifies one of the supported formats.

- Individual image limit: 20 MiB.
- General downloaded Telegram file guard: 50 MiB.
- Images are assigned to the next missing slot based on arrival order.
- The image filename and caption do not choose the scene number.
- The bot replies with the number received and the next missing scene.
- When slots 01–48 all exist, it writes `READY.txt`.

Send scene 01 first, then scene 02, and so on. If you send an image intended for scene 30 first, the receiver will store it as scene 01.

### Upload one ZIP directly to the bot

- ZIP must contain exactly 48 supported image entries (PNG/JPG/JPEG/WebP).
- Downloaded ZIP must be no larger than 50 MiB.
- Each contained image must be no larger than 20 MiB.
- The episode's incoming folder must have no existing scene images.
- ZIP member order is ignored. Images are always sorted by the numbers embedded in their filenames (natural numeric sorting, so `scene-3` comes before `scene-48` and `image_2` before `image_10`). ZIP archive entry order is ignored; the sorted files are assigned to slots 01–48.
- Non-image ZIP entries are ignored.

Use filenames with zero-padded numbers (`scene-01.png`, `scene-02.png`, …) so alphabetical order matches scene order. The receiver does not extract the original directory tree; it reads image entries and writes renamed scene files.

Do not send a ZIP after you have already sent individual scene images. The ZIP will be skipped when the episode already contains images.

## 4. Telegram ZIP Import — stage in GitHub, then import

Workflow: [telegram-zip-import.yml](../.github/workflows/telegram-zip-import.yml)

Use this if you want to upload the ZIP to the repository first instead of sending it through the bot.

1. Commit the ZIP directly into `science-channel/telegram-uploads/` on main.
2. Open Actions → Telegram ZIP Import → Run workflow.
3. Set `episode_path` to the complete episode folder.
4. Set `zip_path` to the ZIP's repository path.
5. Start the workflow.

Example inputs:

```text
episode_path:
science-channel/daily-episodes/2026-11-01/episode-001

zip_path:
science-channel/telegram-uploads/dream.zip
```

The ZIP filename is unrestricted except that it must end in `.zip`; it must be directly in the staging folder, not in a nested directory.

Importer limits and checks:
- ZIP: non-empty, maximum 25 MiB.
- Exactly 48 image entries with PNG/JPG/JPEG/WebP extensions.
- Each image: maximum 20 MiB.
- Rejects absolute archive paths, `..` traversal and symbolic links.
- Rejects duplicate image basenames.
- Refuses to overwrite any existing incoming images.
- Ignores ZIP entry order and always naturally sorts by numeric chunks in filenames (`scene-3` before `scene-48`, `image_2` before `image_10`), then assigns slots 01–48.
- Creates `READY.txt`.

The workflow uses `GH_PAT` as the checkout token and pushes the imported images/READY marker to main. It removes the staged ZIP from the repository after extraction. The resulting push triggers the renderer.

## 5. Planner prompt delivery and finished-video delivery

### Image prompts

After the planner commits the episode package and verifies it exists on main, it sends `image-prompts.md` through Telegram's `sendDocument` API. The caption contains the episode title and the upload folder path.

Prompt delivery is non-blocking. If Telegram credentials are absent, the step skips; if Telegram rejects the document, the episode package remains committed.

### Finished video

After rendering, the workflow uploads the MP4 artifact first (2-day retention), then uses `PonomarevDA/telegram-upload@v1` to send the MP4 to the configured chat.

- Telegram send is non-blocking.
- Successful send enables cleanup of all incoming files except `.gitkeep` and deletion of `READY.txt`.
- Cleanup is committed to main, allowing the same ZIP filename to be reused after the cleanup commit finishes.
- Failed send skips cleanup. The uploaded images/ZIP and READY marker remain available for another attempt.
- The MP4 artifact may already exist even if Telegram delivery fails.

## 6. Modify Telegram behavior — exact code locations

| What you want to change | Edit this | Details |
|---|---|---|
| Bot credentials or destination | Repository Actions secrets | Update `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID`; never hardcode them. |
| Poll interval | `.github/workflows/telegram-image-receiver.yml` | Change `schedule.cron`; keep `workflow_dispatch` if manual polling is desired. |
| Job timeout/Python version | Same receiver workflow | Change `timeout-minutes` or `python-version`. |
| Bot commands/replies | `science-channel/scripts/telegram_image_receiver.py` | Edit command checks and `send()` messages. |
| Incoming chat filter | Same receiver script | Edit comparison with `CHAT_ID`; retain a strict allowlist for security. |
| Supported formats | `image_payload()` and ZIP extension tuple | Update both individual and ZIP handling consistently. |
| File-size limits | Receiver script | Change the 20 MiB individual/ZIP-image checks and 50 MiB download guard. |
| Scene numbering | `scene_numbers()` and image-save logic | Keep numbering range consistent with 48 scenes. |
| Auto-selected episode | `newest_episode()` and selection logic in `main()` | Change sorting or selection policy. Review manual selection persistence. |
| ZIP staging folder/limits | `science-channel/scripts/import_telegram_zip.py` | Change `STAGING_ROOT`, `ALLOWED`, `MAX_ZIP_BYTES`, `MAX_IMAGE_BYTES` and validation. |
| Planner's Telegram document/caption | `.github/workflows/science-channel-daily-planner.yml` | Change the `curl` `sendDocument` fields/caption. |
| Rendered-video Telegram caption | `.github/workflows/free-science-visuals.yml` | Change the upload action's `message` input. |
| Telegram delivery failure behavior | Relevant workflow YAML | Change `continue-on-error` or reorder artifact, delivery and cleanup steps. |

Changing 48 to another count is a coordinated project change: update settings, planner prompts/validation, receiver, ZIP importer, READY logic, renderer, workflow and documentation together. Do not change just one constant.

## 7. Troubleshooting

| Problem | Check |
|---|---|
| No bot response | Check whether the receiver workflow has run; it only is triggered by the Cloudflare Worker webhook. Inspect the Action log and secrets. |
| Bot ignores messages | Confirm the message comes from the exact configured chat ID. |
| Group uploads ignored | Use a private chat or adjust group privacy settings and bot membership. |
| Episode not found | Verify the exact date/episode path and that `episode.json` is already on main. |
| Images saved in unexpected order | Receiver assigns scene slots by arrival order; resend in correct order after safely clearing/resetting the incomplete upload. |
| ZIP not accepted | Check exactly 48 supported images, size limits, and that the incoming folder is empty. |
| 48 images present but no render | Confirm the receiver/importer push to main succeeded and the renderer workflow was triggered by incoming files/READY marker. |
| Telegram video not delivered | Check bot token, chat ID, bot access, action logs and Telegram upload limits. Download the Actions artifact if available. |
| Same ZIP filename cannot be reused | Wait for successful delivery and the cleanup commit to complete on main. |

## 8. Security and branch rules

- Keep bot tokens and PATs in GitHub Secrets only.
- Treat bot tokens as passwords; rotate them if exposed.
- The receiver accepts uploads only from the configured chat ID.
- Do not reset Telegram receiver state without understanding its update offset.
- Science Channel planner, receiver, ZIP importer, renderer and cleanup target `main` only.
- Do not redirect this workflow set to `adaptive-cinematic-effects`.

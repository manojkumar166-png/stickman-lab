# Science Channel — complete operating guide

This guide explains how to create an episode, edit its script, generate and upload images, render the video, and download or delete the result. The pipeline is isolated to `science-channel/` and its two dedicated GitHub Actions workflows.

## How the complete workflow operates

The Science Channel pipeline has two separate GitHub Actions workflows. The first plans an episode and prepares the material; the second turns the completed episode package and its 48 images into a narrated video. Image generation and uploading are the human-in-the-loop part between those two workflows.

### The end-to-end process

```text
Daily schedule or manual start
            |
            v
1. GEMINI DAILY PLANNER
   Chooses one unused science topic
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
   Combines them into final-video.mp4 (no subtitles)
            |
            v
7. OUTPUT ARTIFACT IS UPLOADED
   Topic-based artifact name; retained for 2 days
            |
            v
8. POST-RENDER TASKS
   Attempts Telegram video delivery (non-blocking)
   Attempts to delete processed ZIP from the Git repository
```

### Workflow A — Daily Gemini Planner

- **When it runs:** Automatically once every day at 01:15 UTC (06:45 India Standard Time). You can also manually run **Science Channel — Daily Gemini Planner** as often as you need; there is no one-episode-per-day cap.
- **What each run does:** Every automatic or manual run creates exactly one new episode. Gemini selects a topic that is not in the generated-topic history, writes the episode metadata and complete narration script, and creates exactly 48 numbered scene records. Multiple manual runs on the same date create `episode-001`, `episode-002`, `episode-003`, and so on; earlier episodes are not overwritten.
- **Image prompts:** A second Gemini request creates exactly one visual prompt for each finalized scene. New prompts are told not to add a presenter or talking-head explainer by default; the image should depict the science concept, action, environment or visual metaphor in that scene.
- **What gets saved:** The planner creates the episode folder and its five starter items: `episode.json`, `script.md`, `scenes.json`, `image-prompts.md`, and `images/incoming/.gitkeep`. It also updates the topic history so the topic is not selected again.
- **How it finishes:** The workflow optionally sends `image-prompts.md` to Telegram, then commits the generated Science Channel package to the repository. Telegram is non-blocking: a missing Telegram secret or a send failure does not prevent the episode package commit.
- **What it does not do:** The planner does not generate the 48 image files and does not render the MP4. You generate the images and upload them before rendering.

### The manual creative stage — your review and images

After the planner finishes, you control the episode before it becomes a video. You can edit the title, narration, scene descriptions and image prompts in the episode folder. Generate one image for each final scene prompt, then upload the 48 images into that same episode's `images/incoming/` directory. The renderer does not generate images for you.

If you revise narration after generating images, revise the matching prompt and replace the image too. This keeps what viewers see aligned with what they hear.

### Workflow B — Free Science Visuals Renderer

- **How it starts:** It can run from a push that adds real files to an episode's `images/incoming/` folder (the `.gitkeep` placeholder alone is ignored) or changes its `READY.txt` marker, or you can start **Free Science Visuals — Render Ready Episode** manually in Actions.
- **Choosing the episode:** For a manual run, enter the exact folder in the optional `episode_path` field. If left blank, it chooses the newest episode it finds with a READY marker or incoming image files. For a push run, the changed files must identify exactly one episode; commits affecting multiple episodes are rejected.
- **Validation:** It checks the episode metadata and scene data, requires exactly 48 ordered scene records, checks for 48 numbered narration sections in `script.md`, and requires exactly 48 supported images (either one ZIP or individual files, not a mixture).
- **Rendering:** It converts the images into 16:9 frames, creates spoken narration using Edge TTS and the configured voice, and combines the visuals and narration into `output/final-video.mp4`. **It does not add subtitles or burn captions into the video.**
- **Artifact upload:** After rendering and resolving the topic-based artifact name, it uploads the contents of the episode's `output/` folder as a GitHub Actions artifact. The artifact includes the final MP4 and supporting render files and is retained for **2 days**.
- **After upload:** Telegram video delivery is attempted but is non-blocking. The workflow then tries to delete any processed ZIP archive from the Git repository, with up to three attempts. Individual image files are not automatically deleted.

### What happens if a step fails?

- If the planner fails before committing, a new complete episode package may not be available. Check the planner run's logs in Actions.
- If you have not uploaded all 48 images, or the script/scenes do not pass validation, rendering stops and the rendered artifact is not uploaded.
- If rendering or artifact-name generation fails before the upload step, there is no rendered-video artifact from that run.
- If artifact upload succeeds and a later Telegram or ZIP-cleanup step fails, the workflow run can show **Failed**, but the artifact that was already uploaded remains available until manually deleted or its 2-day retention expires.
- The planner's episode files and uploaded individual images are repository files. The rendered artifact is a separate downloadable item under the Actions run; it is not automatically committed as a video file in the episode folder.

## Quick workflow

1. Run the **Science Channel — Daily Gemini Planner** workflow (or wait for its daily schedule).
2. Open the new episode folder under `science-channel/daily-episodes/YYYY-MM-DD/episode-00N/`.
3. Review or edit `script.md`, `scenes.json`, `episode.json`, and `image-prompts.md`.
4. Generate exactly 48 images from the image prompts.
5. Run `science-channel/scripts/prepare_images.py` to resize/compress the images into one ZIP targeting under 23 MiB, or use Git command line for larger files.
6. Upload that ZIP (or 48 individual images) into that episode's `images/incoming/` folder.
6. Add an empty `READY.txt` file in the episode folder and commit the images and marker. Alternatively, run the render workflow manually and enter the episode folder path.
7. Open the render workflow run, download the artifact, and save the MP4.

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

New Gemini-generated image prompts are instructed **not** to add a presenter, host, teacher, narrator, talking-head character, or recurring man by default. Images should show the actual scientific subject, action, environment, objects, or visual metaphor for that scene. They also request a **1920×1080 landscape (16:9) JPG/JPEG**, with a rough image-size target of **500 KB–2 MB** where the image tool supports export settings. These are prompt targets, not guarantees; the preparation utility below performs the actual resize and compression.

A human figure may appear when the scene itself calls for one, but should be part of the scene rather than standing in front of the viewer and explaining it. For example, a dream-flying scene should show a person soaring through dreamlike clouds and skies, not a man presenting an explanation.

This prompt rule applies to **newly generated episodes**. Existing episode prompt files are not rewritten automatically. Edit an older `image-prompts.md` yourself if you want to apply the new visual direction to that episode.

## 3. Generate and prepare the 48 images

Open that episode's `image-prompts.md`. It contains one prompt for each numbered scene. Generate one image for each prompt, keeping the scene numbers clear.

The prompts request **1920×1080, 16:9 JPG/JPEG** images and suggest roughly **500 KB–2 MB per image** as a quality target. Image generators do not always honor exact file format, dimensions or file size, so run the local preparation utility before uploading. It converts the 48 source images to numbered 1920×1080 JPGs and adjusts JPEG quality as needed to target a ZIP under **23 MiB**, leaving room below GitHub's 25 MB browser-upload limit.

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

**Subtitles are intentionally not generated or burned into the video.**

## 6. Find and download the rendered video

1. Open **Actions** and select the completed **Free Science Visuals — Render Ready Episode** run.
2. Scroll to the **Artifacts** section near the bottom of the run page.
3. Click the artifact named from the episode topic (it starts with `science-channel-`) to download it.
4. Unzip the downloaded artifact. The final video is `final-video.mp4` inside the episode's `output/` contents. Other supporting render files may also be included.

Artifacts are retained for **2 days**. Download the video before the retention period expires. You can delete an artifact earlier from the workflow run's Artifacts section using its delete/trash control.

The artifact upload happens before Telegram delivery and ZIP cleanup. Therefore, if a later Telegram or ZIP-cleanup step fails, an artifact that was already uploaded remains available until it expires or is manually deleted. If rendering or artifact creation fails before the upload step, no rendered-video artifact is created.

## 7. ZIP cleanup and repository files

After the artifact upload, the render workflow attempts to delete processed ZIP archives from the repository's `images/incoming/` folder, retrying up to three times. Individual image files are not automatically deleted. A ZIP-cleanup failure can make the workflow run show as failed even though the video artifact was already uploaded.

## 8. GitHub Actions settings required

In **Settings → Secrets and variables → Actions**:

- Add repository secret `GEMINI_API_KEY` for the planner.
- Optionally add repository variable `SCIENCE_GEMINI_MODEL` to choose the Gemini model.
- Optionally add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository secrets if you want Telegram delivery.

The render workflow installs FFmpeg and Edge TTS itself; no extra repository dependency setup is required.

## 9. What this pipeline changes

Science Channel code, settings, topics, history and episode files are kept under `science-channel/`. Planning and rendering use only these dedicated workflows:

- `.github/workflows/science-channel-daily-planner.yml`
- `.github/workflows/free-science-visuals.yml`

Unrelated repository workflows, scripts, topics, shared configuration and dependencies are outside this pipeline's scope and should not be edited for normal episode production.

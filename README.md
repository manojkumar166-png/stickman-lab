🎬 Automated Daily Science Video Generator

This project is a fully automated Python pipeline that generates high-quality educational science videos. It uses AI for the script, Text-to-Speech for the voice, and FFmpeg for the video rendering. It runs 100% for free using GitHub Actions.

This repository contains **three separate, autonomous workflows** that generate 3 videos per day.

## 📂 Project Structure & File Details

### Core Execution Scripts
- **`main.py`**: The entry point for the **Daily Stickman Workflow**. It calls the story generator, draws 4K anti-aliased stickman artwork using pure Python (Pillow), generates the voiceover, and renders the final video. It is 100% reliable and never touches AI image APIs.
- **`main_ai.py`**: The entry point for the **Cloudflare AI Workflow**. Uses Cloudflare Workers AI (FLUX) to generate beautiful 2D vector illustrations.
- **`main_gemini.py`**: The entry point for the **Gemini AI Workflow**. Uses Google Gemini image generation for all 47 scenes.

### Configuration & Data
- **`config.json`**: The control center. Holds settings for length, scene count, resolution (1280x720), fps, Gemini model, and TTS voice.
- **`topics.txt`**: A seed list of 20 science topics.
- **`topic_history.json`**: The memory. Saves the last 100 topics used so the script doesn't repeat them. The GitHub Action automatically commits this back to your repo.
- **`requirements.txt`**: Python packages (Pillow, requests, edge-tts, aiohttp).

### The `scripts/` Folder (The Engine)
- **`scripts/generate_story.py`**: Connects to Gemini. Writes the 47-scene script. If `topics.txt` is empty, it tells Gemini to invent a brand new topic that matches the *exact style* of your original topics, avoiding everything in the history.
- **`scripts/make_art_python.py`**: The pure Python artist. Draws the 4K anti-aliased stickman images.
- **`scripts/make_art.py`**: The Cloudflare artist. Uses the cheap `flux-2-klein-4b` model. If quota runs out, it reuses previous successful AI images (no stickmen).
- **`scripts/make_art_gemini.py`**: The Gemini artist. Uses only Gemini, no fallback.
- **`scripts/make_voice.py`**: Uses `edge-tts` to convert the script into an MP3. Includes a retry loop to handle Microsoft's temporary network drops.
- **`scripts/render_video.py`**: Uses FFmpeg. Holds the images perfectly still (no panning) and syncs them with the audio at 24fps.

### The `.github/workflows/` Folder
- **`daily-video.yml`**: Runs at **10:00 AM IST**. Generates the pure Python Stickman video.
- **`ai-video-test.yml`**: Runs at **11:00 AM IST**. Generates the Cloudflare AI video.
- **`gemini-video.yml`**: Runs at **12:00 PM IST**. Generates the Gemini AI video.

All three workflows send the finished video to Telegram, including the exact topic name in the message.

---

## ⚙️ How to Customize Everything

### 1. Change the Topics
Open `topics.txt` and add one topic per line. Once the list is used, Gemini takes over and invents new ones forever in the exact same style.

### 2. Change the AI Script Model (Gemini)
Open `config.json`:
- `"gemini-3.5-flash-lite"` (Default - Fastest, best for free tier)

### 3. Change the Voice
Open `config.json`:
- `"en-US-AndrewMultilingualNeural"` (Default - Warm male voice)
- `"en-US-EmmaMultilingualNeural"` (Female voice)
- `"en-GB-RyanNeural"` (British male voice)

### 4. Change Video Length
Open `config.json`:
- `"scene_count": 47` (47 scenes = roughly 8 to 9 minutes).

---

## 🚀 How to Run Locally
Requirements: Python 3.11+, FFmpeg, internet access.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

set GEMINI_API_KEY="your-key"
python main.py
⚠️ Crucial Limits & Rules
GitHub Storage: GitHub gives you 500 MB of free Artifact storage. Download your videos within 7 days.

Telegram Limit: Telegram bots have a 50MB upload limit. If your video is larger, the upload will fail.

Cloudflare Limit: You get 10,000 free neurons per day (resets at 5:30 AM IST). The Cloudflare workflow uses the cheap Klein model to ensure you never run out of quota.

edge-tts: Free Microsoft service. It drops connections occasionally. The script retries automatically up to 5 times.

🔐 GitHub Secrets Required
Add these to your Repository (Settings > Secrets and variables > Actions):

GEMINI_API_KEY

CF_ACCOUNT_ID

CF_API_TOKEN

TELEGRAM_BOT_TOKEN

TELEGRAM_CHAT_ID

text

### 3. Save and Push
```cmd
git pull origin main --rebase
git add README.md
git commit -m "Update README with all three workflows and latest fixes"
git push

---

## 🎥 Science Channel: Upload, Render & Telegram Delivery

The Science Channel rendering workflow runs from **`main`**. Upload scene images or a ZIP archive into the relevant episode's incoming folder:

```text
science-channel/daily-episodes/YYYY-MM-DD/episode-NNN-your-topic/
└── images/
    └── incoming/
        ├── .gitkeep
        └── dream.zip
```

Replace the date and episode folder with the actual episode you want to render. Keep the ZIP directly inside `images/incoming/`; do not put it beside the rendered MP4 or in the episode's top-level folder.

### Reusing the same ZIP filename for testing

You can repeatedly use a filename such as `dream.zip`. After the workflow renders the episode and **successfully sends the video to Telegram**, it automatically:

- Deletes the uploaded ZIP and scene image files from `images/incoming/`.
- Removes the episode's `READY.txt` marker, if present.
- Keeps `.gitkeep`, the episode script and metadata, and the rendered video.
- Commits the upload cleanup to **`main`**.

Once that cleanup commit has reached `main`, upload `dream.zip` again to the same episode folder to run another test. Wait for the previous cleanup to finish before re-uploading the same filename.

**If Telegram delivery fails**, cleanup is skipped and the uploaded files are retained so you can retry. The workflow uses the rendered MP4 as an Actions artifact as well.

### Workflow

- Workflow file: `.github/workflows/free-science-visuals.yml`
- Trigger: a push that adds or changes files under an episode's `images/incoming/` folder or its `READY.txt` marker.
- Manual runs: use **Actions → Free Science Visuals — Render Ready Episode → Run workflow**. You can optionally provide the exact episode folder path.
- Branch: this workflow checks out and commits changes to **`main`**.

Do not upload test ZIPs to `adaptive-cinematic-effects`; the Science Channel upload and rendering process is intended to run on `main`.

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

## 🎵 Copyright-conscious adaptive BGM (Free Visual Science)

The science-channel renderer can automatically select, transition and mix background music by episode topic and narration mood. It does **not** scrape or download music from YouTube.

### Add approved music tracks
1. Download a track yourself from the official [YouTube Audio Library](https://www.youtube.com/audiolibrary) while signed in.
2. Prefer tracks marked **Attribution not required**.
3. Verify the track's current Audio Library terms and keep a record of its title, artist and license.
4. Add the audio file under `science-channel/assets/music/`.
5. Add its metadata to `science-channel/assets/music/library.json`, using this shape:

```json
{
  "tracks": [
    {
      "file": "space/approved-track.mp3",
      "title": "Exact Audio Library track title",
      "artist": "Exact artist name",
      "source": "YouTube Audio Library",
      "license_name": "YouTube Audio Library license",
      "license_url": "https://www.youtube.com/audiolibrary",
      "verified": true,
      "attribution_required": false,
      "topics": ["space", "general"],
      "moods": ["wonder", "inspiring"]
    }
  ]
}
```

Only tracks explicitly marked verified, sourced from YouTube Audio Library, and marked as not requiring attribution are eligible. The renderer records selected track details in `output/bgm-track-record.txt`. If no approved local track is available, rendering continues without BGM. GitHub Actions never downloads music from YouTube.

**Important:** This reduces avoidable music-rights risk but cannot guarantee that a video will never receive a claim or takedown. Recheck the track's license and YouTube Studio copyright checks before public release. Audio Library licensing applies to YouTube use; do not assume it grants rights for other platforms.

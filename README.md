🎬 Automated Daily Science Video Generator

This project is a fully automated Python pipeline that generates high-quality educational science videos. It uses AI for the script, Text-to-Speech for the voice, and FFmpeg for the video rendering. It runs 100% for free using GitHub Actions.

This is the main documentation for the **Daily Stickman Workflow** and the overall project structure.

## 📂 Project Structure & File Details

### Core Execution Scripts
- **`main.py`**: The entry point for the **Daily Stickman Workflow**. It calls the story generator, draws the 4K anti-aliased artwork using pure Python (Pillow), generates the voiceover, and renders the final video. It is 100% reliable and never touches AI image APIs.
- **`main_ai.py`**: The entry point for the **AI Video Experiment**. Uses Cloudflare Workers AI to generate beautiful 2D vector illustrations.

### Configuration & Data
- **`config.json`**: The control center. Holds settings for length, scene count, resolution (1280x720), fps, Gemini model, and TTS voice.
- **`topics.txt`**: A seed list of 20 science topics. 
- **`topic_history.json`**: The memory. Saves the last 100 topics used so the script doesn't repeat them. The GitHub Action automatically commits this back to your repo.
- **`requirements.txt`**: Python packages (Pillow, requests, edge-tts, aiohttp).

### The `scripts/` Folder (The Engine)
- **`scripts/generate_story.py`**: Connects to Gemini. Writes the 47-scene script. If `topics.txt` is empty, it tells Gemini to invent a brand new topic based on science, avoiding everything in the history.
- **`scripts/make_art_python.py`**: The pure Python artist. Draws 4K anti-aliased stickman images for the Stickman workflow.
- **`scripts/make_voice.py`**: Uses `edge-tts` to convert the script into an MP3. Includes a retry loop to handle Microsoft's temporary network drops.
- **`scripts/render_video.py`**: Uses FFmpeg. Takes the images, applies a subtle panning motion (Ken Burns effect), sets the video to 24fps, and syncs it with the audio.

### The `.github/workflows/` Folder
- **`daily-video.yml`**: Runs automatically at **10:00 AM IST**. Generates the pure Python Stickman video and sends it to Telegram.
- **`ai-video-test.yml`**: Runs automatically at **11:00 AM IST**. Generates the AI-illustrated video.

---

## ⚙️ How to Customize Everything

### 1. Change the Topics
Open `topics.txt` and add one topic per line. Once the list is used, Gemini takes over and invents new ones forever.

### 2. Change the AI Script Model (Gemini)
Open `config.json`:
- `"gemini-3.5-flash-lite"` (Default - Fastest)
- `"gemini-3.5-flash"` (Better quality, stricter quota)

### 3. Change the Voice
Open `config.json`:
- `"en-US-AndrewMultilingualNeural"` (Default - Warm male voice)
- `"en-US-EmmaMultilingualNeural"` (Female voice)

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

edge-tts: Free Microsoft service. It drops connections occasionally. The script retries automatically up to 5 times.

🔐 GitHub Secrets Required
GEMINI_API_KEY

TELEGRAM_BOT_TOKEN

TELEGRAM_CHAT_ID

text

### Step 3: Save and Push
```cmd
git add README.md
git commit -m "Update main README with Stickman workflow details"
git push
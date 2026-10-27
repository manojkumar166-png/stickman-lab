🎬 Automated Daily Science Video Generator

This project is a fully automated Python pipeline that generates high-quality, colorful educational science videos. It uses AI for the script, Text-to-Speech for the voice, and FFmpeg for the video rendering. It runs 100% for free using GitHub Actions.

## 📂 Project Structure & File Details

Here is exactly what every file in this project does:

### Core Execution Scripts
- **`main.py`**: The entry point for the **Daily Stickman Workflow**. It calls the story generator, draws the artwork using Python (Pillow), generates the voiceover, and renders the final video. It is 100% reliable and never hits AI image limits.
- **`main_ai.py`**: The entry point for the **AI Video Experiment**. It does the same thing as `main.py`, but uses the Pollinations AI API to download beautiful 2D vector illustrations instead of drawing stickmen.

### Configuration & Data
- **`config.json`**: The control center of the project. It holds settings for target length, scene count, video resolution (1280x720), fps, the Gemini model, and the TTS voice.
- **`topics.txt`**: A plain text list of science topics. The script reads this, picks one randomly (avoiding recent ones), and generates a video for it.
- **`requirements.txt`**: A list of Python packages needed (Pillow, requests, edge-tts, aiohttp).
- **`topic_history.json`**: Automatically created. It saves the last 30 topics used so the script doesn't repeat the same video twice in a row.

### The `scripts/` Folder (The Engine)
- **`scripts/generate_story.py`**: Connects to the Google Gemini API. It sends a strict prompt asking for a 48-scene script in JSON format. It also includes a fallback system: if `gemini-3.5-flash-lite` is overloaded (503 error), it automatically tries `3.5-flash`, then `3.6-flash`.
- **`scripts/make_art.py`**: The artwork generator. 
  - In the *Stickman* workflow, it draws backgrounds and stick figures using Python.
  - In the *AI* workflow, it downloads images from Pollinations, waits 15 seconds between downloads to avoid rate limits, and draws a comic-style title bar and black caption box at the bottom.
- **`scripts/make_voice.py`**: Uses `edge-tts` to convert the text script into an MP3 voiceover.
- **`scripts/render_video.py`**: Uses FFmpeg. It takes the 48 images, applies a smooth panning motion (Ken Burns effect), sets the video to 24fps, and syncs it perfectly with the MP3 audio.

### The `.github/workflows/` Folder
- **`daily-video.yml`**: The automated GitHub Action. Runs every day at 04:30 UTC (10:00 AM IST). It uses `main.py`.
- **`ai-video-test.yml`**: The manual experimental GitHub Action. You run this by clicking a button in the Actions tab. It uses `main_ai.py`.

---

## ⚙️ How to Customize Everything

### 1. How to Change the Topics
Open `topics.txt` and add one topic per line. 
```text
Why do we dream?
Why is the ocean salty?
How do airplanes stay in the air?
2. How to Change the AI Script Model (Gemini)
Open config.json and change "gemini_model":

"gemini-3.5-flash-lite" (Default - Fastest, best for free tier)

"gemini-3.5-flash" (Better writing quality, stricter quota)

"gemini-3.6-flash"

3. How to Change the Voice
Open config.json and change "voice":

"en-US-AndrewMultilingualNeural" (Default - Warm male voice)

"en-US-AriaNeural" (Female voice)

"en-GB-SoniaNeural" (British female)

4. How to Change Video Length
Open config.json:

"scene_count": 48 (48 scenes = roughly 8 to 10 minutes).

"fps": 24 (24 frames per second is standard cinematic quality).

🚀 How to Run It Locally (On Your PC)
Requirements: Python 3.11+, FFmpeg installed, and internet access.

bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate

pip install -r requirements.txt

# Set your API key (Windows PowerShell)
$env:GEMINI_API_KEY="your-google-ai-studio-key"

# Run the Daily (Stickman) version
python main.py

# Run the AI (Experimental) version
python main_ai.py
The final video will be saved in the output/ folder.

☁️ How to Run on GitHub Actions (The Cloud)
Create a new GitHub repository and upload all files.

Go to Settings → Secrets and variables → Actions → New repository secret.

Name: GEMINI_API_KEY | Value: Your Google AI Studio API key.

Go to the Actions tab:

Daily Stickman Science Video: Runs automatically every day. You can also click "Run workflow" to test it.

AI Video Experiment: Click "Run workflow" to manually generate the AI art video.

When the run finishes (green checkmark), scroll to the bottom of the run page and click the Artifacts to download your MP4.

🛠️ Troubleshooting
GEMINI_API_KEY is missing: You forgot to add the secret in GitHub Settings.

Gemini API 404/503: The Google model is overloaded. The script automatically tries fallback models. If all fail, wait a few minutes and try again.

Images look like Stickmen in the AI workflow: The free Pollinations API blocked the request. The script silently falls back to drawing stickmen so the video still works. Try running the AI workflow again later.

FFmpeg missing: Install FFmpeg and ensure ffmpeg -version works in your terminal.

text

Save and close Notepad.

### Step 2: Push the new README to GitHub
Run this in your command prompt:

```cmd
git add README.md
git commit -m "Add highly detailed README with full file structure"
git push

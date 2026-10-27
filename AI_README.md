🎨 AI Video Experiment (Cloudflare Workers AI) - Detailed Guide



This document is the complete technical manual for the \*\*AI Video Experiment\*\* workflow (`ai-video-test.yml`). 



Unlike the production Stickman workflow, this workflow generates stunning, high-quality \*\*2D flat vector illustrations\*\* (like a colorful educational comic) using the \*\*Cloudflare Workers AI (FLUX)\*\* API.



\---



\## 📂 File Structure (What each file does for this workflow)



\### 1. The Execution Script

\- \*\*`main\_ai.py`\*\*: The director. It calls the script generator, downloads the 47 AI images, adds the layout, generates the voiceover, and renders the final MP4.



\### 2. The Engine (`scripts/` folder)

\- \*\*`scripts/generate\_story.py`\*\*: Talks to Gemini. It writes the 47-scene JSON script. If `topics.txt` is empty or fully used, it asks Gemini to invent a brand new topic, avoiding the last 100 topics in `topic\_history.json`.

\- \*\*`scripts/make\_art.py`\*\*: 

&#x20; - Sends the scene descriptions to \*\*Cloudflare\*\* using the `flux-1-schnell` model.

&#x20; - Adds a 6-second pause between each request to stay within free-tier limits.

&#x20; - Draws the blue title bar (top) and black caption box (bottom) over the AI art.

\- \*\*`scripts/make\_voice.py`\*\*: Uses `edge-tts` to generate the MP3 voiceover.

\- \*\*`scripts/render\_video.py`\*\*: Uses FFmpeg. For this workflow, it holds the images completely still (no panning) and syncs them with the audio.



\### 3. The Configuration

\- \*\*`config.json`\*\*: Holds all the settings for this workflow.

\- \*\*`topic\_history.json`\*\*: The memory. Every time a video is made, the topic is saved here. The GitHub Action then pushes this file back to your repository so it never repeats a video.

\- \*\*`topics.txt`\*\*: Your seed list of 20 topics. Once these are used, Gemini takes over and invents new ones forever.



\---



\## 🛠️ How to Change Everything



\### 1. Change the Voice

Open `config.json` and find `"voice"`.

\- \*\*Current:\*\* `"en-US-AndrewMultilingualNeural"` (Warm, natural male voice).

\- \*\*Female alternative:\*\* `"en-US-EmmaMultilingualNeural"`

\- \*\*British male alternative:\*\* `"en-GB-RyanNeural"`



\### 2. Change the AI Art Style

Open `scripts/make\_art.py` and look at the top. You will see the `STYLE` variable:

```python

STYLE = ("flat 2D vector illustration, educational explainer style, clean bold outlines, "

&#x20;        "solid flat colors, limited bright palette, simple geometric shapes, "

&#x20;        "plain light background, no gradients, no text, no photorealism")

You can change this text to whatever you want. For example, if you want a more realistic style, change it to: "photorealistic, cinematic lighting, 4k resolution". (Note: FLUX is best at vector art).



3\. Change the Video Length

Open config.json:



"scene\_count": 47 (Each scene is about 10 seconds. 47 scenes = \~8 minutes).



Warning: Do not increase this number too much! Cloudflare gives you 10,000 free neurons per day. 47 images uses about 4,000 neurons. If you go above 60 scenes, you might hit the daily limit.



4\. Change the AI Model (Cloudflare)

Open scripts/make\_art.py and find the CF\_URL:



python

CF\_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF\_ACCOUNT\_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"

You can change @cf/black-forest-labs/flux-1-schnell to other Cloudflare models (like @cf/stabilityai/stable-diffusion-xl-base-1.0), though FLUX is currently the best for 2D vector art.



5\. Change the Topic Generation

If you want to add more manual topics before Gemini takes over, just add them to topics.txt.



⚠️ Crucial Limits \& Rules

The Cloudflare Daily Quota

You get 10,000 free Neurons per day (resets at 00:00 UTC / 5:30 AM IST).



One video uses \~4,000 Neurons.



Rule: You can safely run this workflow once per day.



Do not click "Run workflow" manually if the automated 11:00 AM run has already finished. You will hit the daily limit and the AI will fail (falling back to stickmen).



The 6-Second Delay

In scripts/make\_art.py, there is a line: time.sleep(6). This is required to avoid Cloudflare's rate limits. If you remove it, the script will crash.



The GitHub Storage Limit

GitHub free tier gives you 500 MB of Artifact storage. Because the AI videos are high quality, they are about 30 MB each.



Rule: The workflow is set to retention-days: 7. Download your videos within a week so they don't delete themselves or fill up your storage.



Automation Schedule

This workflow runs automatically every day at 11:00 AM IST (05:30 UTC) via the ai-video-test.yml file. This is 1 hour after the Stickman workflow, ensuring they don't compete for server resources, and giving Cloudflare time to reset the daily quota.



EMERGENCY: What if Cloudflare stops the free tier?

Cloudflare is currently very generous, but tech companies change their policies all the time. If Cloudflare ever blocks the free tier (returning a 403 Forbidden error) or starts charging money, your workflow will automatically fall back to drawing stickmen.



If you want to keep generating AI art for free, here are your alternate backup plans (ranked from best to worst):



Backup 1: Google Gemini Image Generation (Free Tier)

How it works: You already have a GEMINI\_API\_KEY. Google offers a free tier for image generation (usually around 50-500 requests per day).

The Catch: It is strictly rate-limited (often 1 image per minute). For a 47-scene video, it will take about 45 minutes to generate, and you might hit the daily quota if you run multiple videos.

How to switch: We would modify make\_art.py to use the gemini-2.0-flash (or gemini-2.5-flash-image) endpoint instead of Cloudflare.



Backup 2: Pollinations AI (With a Free Token)

How it works: Pollinations is what we used originally. It blocks GitHub's IP addresses if you don't have a token. If you register a free account at enter.pollinations.ai, they give you an API token. With that token, you can generate images from GitHub Actions.

The Catch: The free tier is slow (about 1 image every 5 seconds) and occasionally returns broken images.

How to switch: We would modify make\_art.py to use the Pollinations URL with your key=YOUR\_TOKEN appended.



Backup 3: Hugging Face (Free Tier)

How it works: Hugging Face is the industry standard for AI. You can create a free account and get an hf\_... token. You can use the black-forest-labs/FLUX.1-schnell model there.

The Catch: The free tier only gives you $0.10 of credits per month. Generating a 47-image video will likely use up your entire monthly quota in one run. It is not viable for daily videos.



Backup 4: Return to Python Stickmen (The Safety Net)

How it works: This is what is already built into your code. If Cloudflare fails, it catches the error and draws a stickman using Python Pillow.

The Catch: You lose the beautiful AI art, but you guarantee a video is produced every single day with zero cost and zero API quotas.



How to switch: You don't have to do anything. The main\_ai.py script is already designed to safely fall back to this if Cloudflare completely breaks.



text



\### Step 3: Push to GitHub

Run these commands:



```cmd

git add AI\_README.md

git commit -m "Update AI README with detailed Cloudflare backup plans"

git push


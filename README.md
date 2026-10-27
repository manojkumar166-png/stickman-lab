# Daily Stickman Science Video Generator

Create one approximately 8-minute colorful stickman science/educational video per day using:
- **AI only for story/script and scene descriptions** (Gemini API; free-tier availability/quotas vary)
- **Python + Pillow** for original cartoon scene artwork
- **edge-tts** for natural-sounding narration (free to use, but it relies on Microsoft's online speech service and availability can change)
- **FFmpeg** for video rendering
- **GitHub Actions** for daily automation

The animation is generated with code, not an AI video-generation service. No paid video-generation API is used.

## Important limits and honest expectations

- ₹0 is the target, **not a guarantee**. Free AI quotas, online TTS availability, GitHub limits, and network downloads can change.
- Gemini API needs a Google AI Studio API key. Create one at https://aistudio.google.com/apikey and add it to your GitHub repository as an Actions secret named `GEMINI_API_KEY`.
- `edge-tts` uses an online service; it is not an offline TTS engine or a guaranteed SLA. The workflow will fail clearly if narration cannot be generated. For a fully offline voice, replace this stage with a locally installed TTS engine/model.
- GitHub Actions scheduled runs are not guaranteed to start at the exact minute. Use a **public repository** if you want standard hosted runner usage without included private-repository minute constraints; review GitHub's current terms.
- The workflow uploads MP4s as Actions artifacts, retained for 7 days. Download each result from the workflow run's **Artifacts** section. It does not publish to YouTube.
- AI-generated science scripts can contain errors. Review the final script/video before publishing.

## Quick start

1. Create a new GitHub repository, e.g. `daily-stickman-science`.
2. Upload all files from this project (keep the `.github/workflows/daily-video.yml` path).
3. In the repository, go to **Settings → Secrets and variables → Actions → New repository secret**.
   - Name: `GEMINI_API_KEY`
   - Value: your Google AI Studio API key.
4. Open **Actions**, enable workflows if prompted, and run **Daily Stickman Science Video** using **Run workflow** for a first test.
5. Open the run when finished and download `stickman-science-video` from Artifacts.
6. The workflow is scheduled daily at 04:30 UTC (10:00 AM India time). Change the cron line in `.github/workflows/daily-video.yml` if desired.

## Run locally

Requirements: Python 3.11+, FFmpeg installed and available as `ffmpeg`, internet access for Gemini and edge-tts.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
python main.py
```

On Windows PowerShell:
```powershell
$env:GEMINI_API_KEY="your-key"
python main.py
```

Output is written to `output/`. The main MP4 is `output/stickman-science-YYYY-MM-DD.mp4`; the script and scene plan are saved beside it.

## Customize

- Edit `config.json` to change visual style, number of scenes, target length, voice, and output frame rate.
- Edit `topics.txt` to add your own topic ideas. The script selects one that hasn't been used recently where possible.
- This starter version creates 24–40 scenes with colorful illustrated backgrounds and a reusable stickman design. It uses slow camera movement for visual variety.
- Do not commit API keys to the repository. Use GitHub Secrets.

## Troubleshooting

- **No GEMINI_API_KEY**: add the secret; never hardcode it.
- **Gemini quota/rate limit**: wait for quota reset or choose another available model in `config.json`.
- **edge-tts fails**: check network/service availability and rerun; the project currently stops rather than silently making a video with no narration.
- **FFmpeg missing**: install FFmpeg and ensure `ffmpeg -version` works.
- **Video takes a while**: 8 minutes of video encoding is CPU-intensive. The workflow uses 12 fps and 720p to keep rendering manageable.

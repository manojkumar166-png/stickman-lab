# Free Stickman Studio

A no-API, no-subscription 2D stickman video generator that runs on GitHub Actions.

## What is free

- Python and Pillow draw the scenes locally on the GitHub-hosted runner.
- FFmpeg encodes the MP4.
- The workflow uses no Gemini, OpenAI, Claude, ElevenLabs, paid image APIs, paid stock assets, or API secrets.
- Storyboard and MP4 are uploaded as a GitHub Actions artifact.

GitHub Actions usage is subject to GitHub's current plan, repository visibility, and runner-minute limits. Public repositories generally have free standard GitHub-hosted runner usage; private repositories may consume included minutes or incur charges after the allowance. Check your plan before running many long renders.

## Run it

1. Open this repository on GitHub.
2. Select **Actions**.
3. Select **Free Stickman Studio**.
4. Choose **Run workflow**.
5. Enter a title and story, then choose duration, resolution and FPS.
6. When the run completes, open its **Artifacts** section and download the ZIP.

No repository secrets are required.

## Run locally

Requirements: Python 3.11+, FFmpeg/FFprobe, and Pillow.

```bash
python -m pip install "Pillow>=10,<13"
python scripts/free_stickman_studio.py \
  --title "The Door to Tomorrow" \
  --story "A stickman finds a glowing door, opens it, and meets a friend." \
  --seconds 20 --fps 24 --width 1280 --height 720
```

Output files are written to `output/free-stickman/`:
- `stickman-short.mp4`
- `storyboard.json`
- `storyboard.md`

## Important limitations

This first zero-cost path is deterministic 2D animation. It converts story sentences into scene beats and uses keyword-based action selection. It does not call an AI model, so it will not invent sophisticated plots or understand every natural-language instruction. It currently renders simple stick-figure movement, basic props, captions and procedural backgrounds. It does not provide voice cloning, generated narration, AI images, or advanced 3D character rigging.

The existing 3D and AI-assisted workflows remain separate experiments. They may use optional anonymous model endpoints or free-tier services; those services can change availability, impose limits, or require credentials. Use **Free Stickman Studio** when you want the guaranteed no-API baseline.

## Security and cost

The workflow has read-only repository permissions, does not commit generated files to the repository, and stores output as a temporary artifact for 14 days. It does not require Telegram tokens, Cloudflare credentials, model API keys, or any other secrets.

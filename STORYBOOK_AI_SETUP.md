# Automated AI storybook science visuals

This workflow generates one original text-to-image illustration per scene with Cloudflare Workers AI, then uses a Chromium/HTML/CSS compositor to add consistent story branding and assembles the stills into a video with FFmpeg.

## Required GitHub Actions secrets

In **Settings → Secrets and variables → Actions**, add:

- `GEMINI_API_KEY` — used by the existing story/narration planner.
- `CLOUDFLARE_ACCOUNT_ID` — your Cloudflare account ID.
- `CLOUDFLARE_API_TOKEN` — a token permitted to run Workers AI inference for that account.

The image provider is Cloudflare Workers AI using `@cf/black-forest-labs/flux-1-schnell`. Cloudflare documents a free allocation of 10,000 Neurons per day, reset at 00:00 UTC. This is a shared account-level allowance; large scene counts or other AI usage can exhaust it. If the provider returns a quota, access, or capacity error, the workflow fails visibly and does not quietly replace the requested artwork with procedural drawings.

## Run it

Open **Actions → Free Science Visuals — AI Storybook 2D → Run workflow**, or use **Daily Stickman Science Video — AI Storybook 2D**.

## Visual pipeline

1. Python creates the story and scene plan.
2. Cloudflare Workers AI generates a distinct image prompt result for every scene.
3. Chromium renders each still through an HTML/CSS finishing layer (branding, typography, subtle grain and gradients).
4. Python/FFmpeg assembles still images with narration. Still frames remain static; no camera motion is added.

The image credits JSON includes the model and prompts for traceability. The generated image model is an external hosted service, so the repository itself does not need a GPU. The Cloudflare account must have Workers AI access enabled.

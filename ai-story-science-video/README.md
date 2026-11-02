# AI Story & Science Video Creator

A standalone workflow that turns Gemini's story plan into a narrated MP4.

## Modes
- Science documentary: Gemini invents or follows a subject, writes a responsible explanatory script, and creates scene-by-scene visual prompts.
- Animated story: Gemini creates an original story with recurring characters, a continuity bible, narration, scene descriptions and visual prompts.

## Pipeline
1. Gemini creates a complete ordered script and scene plan.
2. Each scene receives a detailed image prompt.
3. Every scene image is generated using anonymous OVHcloud SDXL, with anonymous Pollinations as fallback.
4. All images are validated. If any scene image is missing or invalid, rendering stops.
5. Edge TTS creates narration for each scene.
6. FFmpeg combines each scene image and its narration, then joins all segments into one MP4.
7. The MP4, story JSON, readable script and images are uploaded as a 7-day artifact.

## Run
Open Actions, select AI Story & Science Video Creator, and choose Run workflow. Select science or animated, optionally enter a topic, choose 6/8/10/12/16 scenes and a voice.

## Required secret
Add GEMINI_API_KEY under repository Settings, Secrets and variables, Actions. No Zhipu, Stability, OVH token, Cloudflare or payment secret is used.

## No-card safeguards
- OVHcloud is called anonymously; no OVH API token is read.
- Pollinations is called anonymously.
- No credit purchases, auto-recharge or paid image-provider fallback is implemented.
- Anonymous provider access can throttle or become unavailable; no unlimited free service is guaranteed.
- Gemini and GitHub Actions have separate account quotas and terms. Do not enable billing if you want a strict no-card setup.

## Output package
story.json, script.md, images/scene-XX.png, audio/scene-XX.mp3, segments/segment-XX.mp4 and final-video.mp4. The uploaded artifact contains the final MP4, script, plan and scene images.


## Gemini model configuration
The workflow defaults to `gemini-3.8-flash` and falls back to `gemini-3.5-flash-lite`. These defaults were updated after Gemini API returned 404 for the retired/unavailable 2.5 and 2.0 model IDs. You can override them with repository variables `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`.

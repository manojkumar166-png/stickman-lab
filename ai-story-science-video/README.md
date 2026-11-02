# AI Story & Science Video Creator

A standalone workflow following the AI Video Experiment's end-to-end pattern—Gemini story, per-scene artwork, Edge TTS narration, FFmpeg rendering and artifact upload—but using free anonymous image providers instead of Cloudflare. Supports 6–48 scenes, including 48-image long-form videos.

## Gemini-led creation
There is no manual science/animated mode selector. Optionally supply a topic or leave it blank. Gemini first reads the root-level topics.txt inspiration library, studies its broad subject areas and curiosity-driven style, then invents a genuinely new topic—not an exact match, paraphrase or near-duplicate. An optional topic input is treated only as an extra interest hint. Gemini then decides whether the new idea works best as a science documentary or an original animated story. It then creates the script, continuity bible and scene-by-scene visual prompts.

## Topic inspiration file

Edit the repository-root topics.txt to control the subject areas and curiosity-driven style that inspire new ideas. Gemini reads every non-empty, non-comment line on each run. It must create a distinct topic rather than copy or lightly rephrase an entry. Keep this file populated; the workflow stops with a clear error if it is missing or empty.

## Pipeline
1. Gemini creates a complete ordered script and scene plan.
2. Each scene receives a detailed image prompt.
3. Each scene tries several routes in order: anonymous OVHcloud SDXL (rate-limited to about one request every 35 seconds), anonymous AI Horde volunteer workers, Vexa's anonymous DeepAI/Flux image endpoint, then direct Pollinations. OVHcloud receives a retry; the remaining providers are fallbacks.
4. All images are validated. If any scene image is missing or invalid, rendering stops. The Actions log reports provider attempts and scene-by-scene progress.
5. Edge TTS creates narration for each scene.
6. FFmpeg combines each scene image and its narration, then joins all segments into one MP4.
7. The MP4, story JSON, readable script and images are uploaded as a 7-day artifact.

## Run
Open Actions, select AI Story & Science Video Creator, and choose Run workflow. Optionally enter an interest hint (or leave it blank), choose 6/8/10/12/16/48 scenes and a voice. Gemini reads topics.txt, invents a distinct new topic in a similar spirit, then chooses science documentary or animated story.

## Required secret
Add GEMINI_API_KEY under repository Settings, Secrets and variables, Actions. No Zhipu, Stability, OVH token, Cloudflare or payment secret is used.

## No-card safeguards
- OVHcloud is called anonymously; no OVH API token is read.
- AI Horde uses its public anonymous key; anonymous jobs have the lowest queue priority and can take longer.
- Vexa is a community-hosted multi-provider gateway; its availability and upstream providers can change.
- Pollinations is called anonymously as the final fallback.
- No credit purchases, auto-recharge or paid image-provider fallback is implemented.
- Anonymous provider access can throttle, queue for a long time, change terms, or become unavailable; no unlimited free service is guaranteed. Vexa's Flux route may itself use Pollinations upstream, so it is not fully independent of Pollinations.
- Gemini and GitHub Actions have separate account quotas and terms. Do not enable billing if you want a strict no-card setup.

## Output package
story.json, script.md, images/scene-XX.png, audio/scene-XX.mp3, segments/segment-XX.mp4 and final-video.mp4. The uploaded artifact contains the final MP4, script, plan and scene images.


## Gemini model configuration
The workflow defaults to `gemini-3.8-flash` and falls back to `gemini-3.5-flash-lite`. These defaults were updated after Gemini API returned 404 for the retired/unavailable 2.5 and 2.0 model IDs. You can override them with repository variables `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`.


## Visible progress and 48-scene runs

The job timeout is six hours to accommodate long anonymous-provider queues. The Actions log prints the run configuration, Gemini planning, image-provider attempts, image validation, Edge TTS narration, FFmpeg rendering and final MP4 validation. GitHub Actions separately shows dependency installation, artifact resolution and artifact upload. A 48-scene run creates 48 individual images; free services may queue or throttle requests and may still fail before the timeout.

## Original 3D CGI visual direction

Image prompts request polished cinematic 3D CGI, detailed materials, depth and lighting. Animated stories use expressive original character designs and continuity notes. Science videos use cinematic 3D scientific visualisations. Prompts explicitly avoid copying existing studios, films, franchises, copyrighted characters or named artists. This does not guarantee every free image provider will interpret the prompt identically.

## Image provider difference from AI Video Experiment

The legacy AI Video Experiment uses Cloudflare Workers AI. This workflow deliberately does not copy that image backend: it uses anonymous OVHcloud SDXL, AI Horde, Vexa and Pollinations as its fallback chain. The rest of the production pattern is similar: Gemini planning, per-scene artwork, Edge TTS, FFmpeg and downloadable GitHub Actions artifacts.

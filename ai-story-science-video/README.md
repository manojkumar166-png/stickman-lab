# AI Story & Science Video Creator

A standalone one-click workflow: Gemini invents a topic, creates a 48-scene plan, free anonymous image providers generate 48 images, Edge TTS creates narration, and FFmpeg renders the final MP4. It does not use Cloudflare for image generation and does not require a paid image API key.

## Gemini-led creation
There is no manual science/animated mode selector and no manual topic input in the current workflow. Gemini reads the root-level topics.txt inspiration library, studies its broad subject areas and curiosity-driven style, then invents a genuinely new topic—not an exact match, paraphrase or near-duplicate. Gemini decides whether the idea works best as a science documentary or an original animated story, then creates the script, continuity bible and 48 scene-by-scene visual prompts.

## Topic inspiration file

Edit the repository-root topics.txt to control the subject areas and curiosity-driven style that inspire new ideas. Gemini reads every non-empty, non-comment line on each run. It must create a distinct topic rather than copy or lightly rephrase an entry. Keep this file populated; the workflow stops with a clear error if it is missing or empty. Previously completed topics are tracked separately in used_story_topics.json, so editing topics.txt does not erase the no-repeat history.

## Pipeline
1. Gemini creates a complete ordered script and scene plan.
2. Each scene receives a detailed image prompt.
3. Each scene tries several routes in order: anonymous OVHcloud SDXL (spaced about 31 seconds apart to stay below its anonymous rate limit), anonymous AI Horde volunteer workers, Vexa's anonymous DeepAI/Flux image endpoint, then direct Pollinations. OVHcloud receives a retry; the remaining providers are fallbacks.
4. All images are validated. If any scene image is missing or invalid, rendering stops. The Actions log reports provider attempts and scene-by-scene progress.
5. Edge TTS creates narration for each scene.
6. FFmpeg combines each scene image and its narration, then joins all segments into one MP4.
7. The MP4, story JSON, readable script and images are uploaded as a 7-day artifact.

## Run — one click, 48 scenes
1. Open the repository's **Actions** tab.
2. Select **AI Story & Science Video Creator**.
3. Click **Run workflow**.
4. Select branch **main** and click **Run workflow** again.

There are no input fields. Every run automatically asks Gemini for a fresh topic, creates 48 scenes/images and uses the default voice `en-US-AndrewMultilingualNeural`.

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
During the run, the job creates story.json, script.md, images/scene-XX.png, audio/scene-XX.mp3, segments/segment-XX.mp4 and final-video.mp4. The workflow then attempts to publish the used-topic history in an isolated Git worktree with fetch-and-retry handling. This bookkeeping step is non-blocking: a concurrent `main` update or history-sync failure must not prevent the rendered video from reaching subtitle generation. Next, faster-whisper generates synchronized phrase-level captions in a separate `.srt` file. The video itself is **not modified**: subtitles are not burned into the picture, and viewers can enable or disable them in a compatible player. The workflow names both files from the story title (`Story Title.mp4` and `Story Title.srt`), validates them, and uploads both together as a 7-day GitHub Actions artifact. Telegram delivery sends the title-named MP4; download the matching SRT from the artifact when you need a separate subtitle file.


## Gemini model configuration
The workflow defaults to `gemini-3.8-flash` and falls back to `gemini-3.5-flash-lite`. These defaults were updated after Gemini API returned 404 for the retired/unavailable 2.5 and 2.0 model IDs. You can override them with repository variables `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`.


## Visible progress and 48-scene runs

The job timeout is six hours to accommodate long anonymous-provider queues. The Actions log prints the run configuration, Gemini planning, image-provider attempts, image validation, Edge TTS narration, FFmpeg rendering and final MP4 validation. GitHub Actions separately shows dependency installation, artifact resolution and artifact upload. A 48-scene run creates 48 individual images; free services may queue or throttle requests and may still fail before the timeout.

## Original 3D CGI visual direction

Image prompts request polished cinematic 3D CGI, detailed materials, depth and lighting. Animated stories use expressive original character designs and continuity notes. Science videos use cinematic 3D scientific visualisations. Prompts explicitly avoid copying existing studios, films, franchises, copyrighted characters or named artists. This does not guarantee every free image provider will interpret the prompt identically.

## Image provider difference from AI Video Experiment

The legacy AI Video Experiment uses Cloudflare Workers AI. This workflow deliberately does not copy that image backend: it uses anonymous OVHcloud SDXL, AI Horde, Vexa and Pollinations as its fallback chain. The rest of the production pattern is similar: Gemini planning, per-scene artwork, Edge TTS, FFmpeg and downloadable GitHub Actions artifacts.


## Change the workflow defaults

The Actions screen intentionally has no inputs. Change settings by editing the files in the repository and committing the change to `main`.

| Setting | File and exact place |
|---|---|
| Scene count (currently 48) | `.github/workflows/ai-story-science-video.yml` — change `--scenes 48` in the Python command. The script accepts 4–48. |
| Narration voice | Same YAML command — change the value after `--voice`. |
| Fixed topic instead of Gemini choosing | Same YAML command — replace `--topic ""` with `--topic "your topic here"`. Leave it blank for automatic topic selection. |
| Topic inspiration and subject variety | Root `topics.txt` — add or remove one inspiration per line. |
| Gemini model and fallback | Repository Settings → Secrets and variables → Actions → Variables: `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`. |
| Cinematic image prompt style/framing | `scripts/ai_story_video.py`, function `generation_prompt()`. |
| Image providers, order, retries and pacing | Same Python file: `ovh()`, `ai_horde()`, `vexa()`, `pollinations()` and `generate_all()`. |
| Video encoding | Same Python file, function `render()`. |
| Subtitle generation and SRT formatting | `science-channel/scripts/karaoke_subtitles.py` (`generate_karaoke_srt`). The workflow creates a separate title-matched `.srt`; it does not burn captions into the MP4. |
| Topic-history push conflicts | The history step uses a separate worktree, refreshes `origin/main` on each retry, merges the generated topic into the latest JSON list without duplicating its core topic, and is marked non-blocking so subtitles and delivery can continue. A warning means topic history may need manual repair; it does not mean the video should be discarded. |
| Artifact and Telegram delivery | `.github/workflows/ai-story-science-video.yml`. |

The exact one-click command is:

```bash
python -u scripts/ai_story_video.py --topic "" --scenes 48 --voice "en-US-AndrewMultilingualNeural"
```

The workflow index and repository-wide editing guidance are in [`.github/workflows/README.md`](../.github/workflows/README.md) and the [root README](../README.md).

## Runtime expectations

Forty-eight images are generated sequentially. Anonymous image services have queues and rate limits; OVHcloud spacing alone adds roughly 24 minutes across 48 scene requests, before actual image-generation time, provider fallbacks, narration, subtitles and video rendering. This is a no-card design, not an instant-generation guarantee. Reducing the scene count in the workflow command is the most direct way to shorten a run.

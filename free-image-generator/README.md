# Free Image Generator

An independent GitHub Actions workflow for image generation using free API access and automatic fallback. Cloudflare is intentionally excluded because it is already used by the AI Video Experiment.

## Run it

Open **Actions → Free Image Generator → Run workflow**. Enter a prompt and optional dimensions. A scheduled run also executes daily at 11:30 AM IST with a default science illustration prompt.

## Provider order

1. OVHcloud AI Endpoints — SDXL (catalog-listed Free; anonymous rate-limited access).
2. Zhipu AI — CogView-3-Flash (listed as free; account concurrency/eligibility applies).
3. Stability AI — Stable Image Core (25 one-time introductory credits).
4. Pollinations Free API Classic (anonymous, best-effort, rate-limited).

The generator retries transient failures, skips providers without required keys, validates image bytes, and moves to the next provider. It never calls Cloudflare or a paid-only provider. Stability's initial credits are finite and are not replenished automatically. If every provider fails, the workflow fails and records the reason.

See [API audit](API_AUDIT.md) for quotas, limitations, exclusions, and source links.

## Required GitHub Actions secrets

- `ZHIPU_API_KEY`
- `STABILITY_API_KEY`
- `OVH_AI_ENDPOINTS_ACCESS_TOKEN` (optional)

Generated images and the provider log are uploaded as a workflow artifact for 14 days. This workflow does not modify or invoke any existing workflow.

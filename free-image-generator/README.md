# Free Image Generator

An independent GitHub Actions workflow for generating images through free-tier image APIs with automatic fallback.

## Run it

Open **Actions → Free Image Generator → Run workflow**. Enter a prompt and optional dimensions. A scheduled run also executes daily at 11:30 AM IST with a default science illustration prompt.

## Providers

1. Cloudflare Workers AI — FLUX.1 schnell (10,000 Neurons/day free allocation).
2. OVHcloud AI Endpoints — Stable Diffusion XL (catalog-listed Free model).

The generator retries transient failures, skips permanent credential/model errors, validates image bytes, and moves to the next provider. It never calls a paid provider. If both providers fail, the workflow fails and records the reason.

See [API audit](API_AUDIT.md) for current quotas, setup requirements, exclusions, and source links.

## Required GitHub Actions secrets

- `CF_ACCOUNT_ID`
- `CF_API_TOKEN`\n- Repository variable `CF_WORKERS_FREE_PLAN_CONFIRMED=true` only if the account is on Workers Free (leave unset on Workers Paid)
- `OVH_AI_ENDPOINTS_ACCESS_TOKEN`

Add keys under **Settings → Secrets and variables → Actions**. Set the Cloudflare confirmation variable only if your account is on the Workers Free plan. The Cloudflare provider is disabled by default until this is explicitly confirmed. Do not commit keys.

Generated images and the provider log are uploaded as a workflow artifact for 14 days. This workflow does not modify or invoke any existing workflow.

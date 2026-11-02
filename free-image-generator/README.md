# Free Image Generator

An independent GitHub Actions workflow for image generation using no-card access paths and sequential provider fallback. Cloudflare is intentionally excluded because it is already used by the AI Video Experiment.

## Run it

Open **Actions → Free Image Generator → Run workflow**. Enter a prompt and optional dimensions. A scheduled run also executes daily at 11:30 AM IST with a default science illustration prompt.

## Provider order

1. OVHcloud AI Endpoints — SDXL through its anonymous endpoint only (no token/payment method).
2. Zhipu AI — CogView-3-Flash, only if you configure an API key after confirming free access in your account.
3. Pollinations Free API Classic — anonymous, best-effort, rate-limited.

The workflow does not read OVHcloud credentials, Stability credentials, Cloudflare credentials, or payment credentials. It contains no credit purchasing, auto-top-up, or paid fallback logic. Providers may throttle or change their free access; if all fail, the workflow fails and records the reasons.

See [API audit](API_AUDIT.md) for caveats and excluded providers.

## Optional GitHub Actions secret

- `ZHIPU_API_KEY` — only add this if the Zhipu console confirms CogView-3-Flash is free for your account. OVHcloud anonymous access and Pollinations need no key.

Generated images and the provider log are uploaded as a workflow artifact for 14 days. This workflow does not modify or invoke any existing workflow.

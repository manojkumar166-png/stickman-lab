# No-card image API audit (2 November 2026)

This workflow is intentionally configured for providers that can be attempted without adding a payment card. Cloudflare is excluded because it is already used by the AI Video Experiment.

## Enabled providers

| Priority | Provider / model | Access | No-card safeguards and caveats |
|---|---|---|---|
| 1 | OVHcloud AI Endpoints — Stable Diffusion XL base 1.0 | Anonymous endpoint; no API token is sent | Anonymous access is rate-limited (documented at 2 requests/minute per IP/model). The authenticated route is deliberately disabled and no OVH token secret is read. If anonymous access stops working, the workflow skips it. |
| 2 | Zhipu AI — CogView-3-Flash | User-supplied `ZHIPU_API_KEY` | Confirm in the Zhipu console that this model is still free for your account before adding a key. Account-specific eligibility, concurrency, and quotas apply. No payment details are configured by this workflow. |
| 3 | Pollinations Free API Classic | Anonymous, no account/key | Best-effort free service; throttling and availability can vary. |

## Deliberately excluded

| Provider | Reason |
|---|---|
| Stability AI | Removed from the automatic chain because introductory credits are finite and the no-card eligibility/activation path is not sufficiently guaranteed for this setup. |
| Hugging Face Inference Providers | Small free monthly allowance, routed third-party inference and possible billing after the allowance; not enabled until a robust no-billing cap can be guaranteed. |
| Replicate | Free runs are limited and continuing generally requires billing/credits. |
| Together AI / fal.ai | No dependable no-card free image quota verified for this workflow. |
| Google Gemini image models | No generally available free API image-generation allowance verified. |
| YepAPI and other trial-credit aggregators | Trial terms and card requirements vary; not enabled without direct verification. |
| Cloudflare | Deliberately excluded; reserved for the existing AI Video Experiment. |

## No-card safety rules

- The workflow does not read or pass any credit-card, billing, or payment credentials.
- The OVHcloud authenticated route is disabled; only its anonymous endpoint is attempted.
- No automatic credit purchase, top-up, or paid fallback exists in the code.
- Zhipu is only called when `ZHIPU_API_KEY` is configured; verify its free status in your own account before adding it.
- Anonymous services may rate-limit or stop responding. Failures move to the next provider.
- If all enabled providers fail, the job fails visibly. It does not fabricate an image or report success.

## GitHub Actions secrets

Only one optional secret is used:

- `ZHIPU_API_KEY` — add only if the Zhipu console confirms free CogView-3-Flash access for your account.

OVHcloud and Pollinations require no secret in this workflow. No Stability, Cloudflare, or billing secrets are read.

## Primary sources

- OVHcloud SDXL catalog: https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/stable-diffusion-xl/
- OVHcloud API capabilities and anonymous rate limits: https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities
- Zhipu pricing/model availability: https://open.bigmodel.cn/pricing
- Zhipu image generation API: https://open.bigmodel.cn/dev/api#cogview
- Pollinations service/privacy: https://enter.pollinations.ai/privacy
- Stability AI pricing and credit terms (provider excluded): https://platform.stability.ai/pricing
- Hugging Face inference pricing (provider excluded): https://huggingface.co/docs/inference-providers/pricing
- Replicate Try for Free terms (provider excluded): https://replicate.com/collections/try-for-free

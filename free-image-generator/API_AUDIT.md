# Free image API audit (2 November 2026)

Cloudflare is deliberately excluded from this generator because the repository owner already uses that account for the AI Video Experiment. This workflow does not read Cloudflare credentials or call Cloudflare.

## Provider order in this workflow

| Priority | Provider / model | Free access model | Authentication | Important limits / caveats |
|---|---|---|---|---|
| 1 | OVHcloud AI Endpoints — Stable Diffusion XL base 1.0 | Catalog-listed Free model | Anonymous access works; optional `OVH_AI_ENDPOINTS_ACCESS_TOKEN` | Anonymous: 2 requests/minute per IP and model. Authenticated: up to 400/minute/project. API key setup requires a Public Cloud project and payment method; use only the endpoint explicitly marked Free. |
| 2 | Zhipu AI — CogView-3-Flash | Model listed as free on Zhipu Open Platform | `ZHIPU_API_KEY` | Account concurrency limits apply. Account eligibility/identity checks may apply; availability and limits are account-specific. Confirm model remains marked Free in console. |
| 3 | Stability AI — Stable Image Core | New-account introductory 25 credits | `STABILITY_API_KEY` | One-time credits, not recurring. Core costs 3 credits per image (roughly 8 images). After credits are exhausted the API fails; this workflow does not purchase credits. |
| 4 | Pollinations Free API Classic | Anonymous no-account classic image endpoint, best-effort free access | No key | Rate-limited/abuse-controlled and availability can vary. Not a guaranteed throughput tier; service may return throttling or temporary errors. |

## Providers researched but not enabled

| Provider | Why it is not in the automatic free-only chain |
|---|---|
| Hugging Face Inference Providers | Free accounts receive only $0.10/month routed inference credit; beyond that is pay-as-you-go. Too small and can route to billable third-party providers. |
| Replicate | Try-for-free models have limited free runs; after the cap, users must add billing and purchase credits. |
| Together AI | No generally available recurring free image-generation allocation verified. |
| fal.ai | Image inference is paid; no guaranteed free API allowance verified. |
| Google Gemini image models | Image generation is not included in the normal free API tier. |
| YepAPI | Advertises one-time promotional credit, not a recurring free model API. |
| NVIDIA NIM and other hosted inference catalogs | No dependable, public recurring free image-generation API quota verified for this use. |

## Free-only safeguards

- Cloudflare is not present in the provider list and no Cloudflare secret is passed to this workflow.
- No paid-only provider is called.
- Stability's initial credits are finite; the workflow does not buy more credits.
- Providers without configured keys are skipped.
- Temporary errors (408, 409, 425, 429, 5xx, and network errors) are retried up to three times before moving on.
- Permanent authentication/model errors skip that provider immediately.
- Every response is validated as an image and normalized to PNG.
- If all providers fail, the job fails visibly. It does not fabricate an image or report success.

## Required GitHub Actions secrets

- `ZHIPU_API_KEY`
- `STABILITY_API_KEY`
- `OVH_AI_ENDPOINTS_ACCESS_TOKEN` (optional; anonymous OVH access is also attempted)

No Cloudflare secrets are required by this workflow.

## Primary sources

- OVHcloud free SDXL catalog: https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/stable-diffusion-xl/
- OVHcloud API capabilities and limits: https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities
- Zhipu CogView-3-Flash model/pricing listing: https://open.bigmodel.cn/pricing (check account-specific model availability and current free status)
- Zhipu image generation API: https://open.bigmodel.cn/dev/api#cogview
- Stability AI pricing (25 introductory credits; Stable Image Core 3 credits): https://platform.stability.ai/pricing
- Stability AI API authentication and credits: https://platform.stability.ai/docs/getting-started
- Pollinations Free API Classic privacy/service description: https://enter.pollinations.ai/privacy
- Hugging Face inference pricing: https://huggingface.co/docs/inference-providers/pricing
- Replicate Try for Free terms: https://replicate.com/collections/try-for-free
- Current comparative audit (cross-check only; verify vendor terms before use): https://aifree.dev/learn/free-image-generation-api

# Free image API audit (2 November 2026)

This audit is used by the independent **Free Image Generator** workflow. A provider is enabled only when its documented API can be used without triggering paid usage. The workflow does not call paid fallbacks.

## Enabled fallback providers

| Priority | Provider / model | Free allowance | Authentication | API / response | Notes |
|---|---|---|---|---|---|
| 1 | Cloudflare Workers AI — `@cf/black-forest-labs/flux-1-schnell` | 10,000 Neurons per account per UTC day on Workers Free; requests fail after the free allocation is exhausted | `CF_ACCOUNT_ID` and `CF_API_TOKEN` GitHub Secrets | Cloudflare account AI REST endpoint; image bytes or base64 result | Daily quota is shared with other Workers AI usage in the account. Do not upgrade/enable paid usage for this workflow. |
| 2 | OVHcloud AI Endpoints — `stable-diffusion-xl-base-v10` | Model catalog lists this endpoint as Free; anonymous limit is 2 requests/minute/IP, authenticated limit 400/minute/project | `OVH_AI_ENDPOINTS_ACCESS_TOKEN` GitHub Secret | SDXL endpoint returns image bytes; OpenAI-compatible endpoint also documented | OVH requires a Public Cloud project with a payment method to create/use authenticated keys. The model is listed Free, but monitor project usage and confirm the displayed price remains Free before use. |

## Evaluated but not enabled as a guaranteed-free fallback

| Provider | Current finding | Decision |
|---|---|---|
| Stability AI | 25 introductory credits; credits are consumed per image and then additional credits must be purchased | Excluded from automatic fallback because the free allowance is one-time and must not become paid usage. |
| Hugging Face Inference Providers | Free accounts receive $0.10 monthly credits; extra usage requires purchased credits | Excluded: small metered credit, not a durable no-cost model endpoint. |
| Pollinations | Current unified image API requires an API key and spends Pollen; model catalog is public but generation is balance-based | Excluded: free-looking legacy endpoints are not a reliable guaranteed-free API allowance. |
| Replicate | Some models offer free trial runs, with unpublished run counts; usage can become billable | Excluded: trial-only and unclear quota. |
| Google Gemini image models | Image generation is not included in the free Gemini API tier according to the current API pricing audit | Excluded. |
| Together AI / fal.ai / OpenAI / Runway / BFL / Ideogram | Current image inference is paid or requires prepaid credits | Excluded. |

## Workflow behavior

- Manual trigger accepts a prompt, width, and height.
- Scheduled trigger runs daily at 11:30 AM India time and uses a built-in science illustration prompt.
- Provider order is Cloudflare, then OVHcloud.
- Each provider gets up to three attempts for transient network, 408, 409, 425, 429, and 5xx failures.
- Permanent 4xx errors skip retries and move to the next provider.
- Images are verified with Pillow and normalized to PNG before success is reported.
- Provider attempts and failures are written to `free-image-generator/provider-log.jsonl`.
- If all providers fail or no provider secrets are configured, the workflow fails visibly. It never reports a fake success and never calls a paid provider.

## Secrets to configure

- `CF_ACCOUNT_ID`
- `CF_API_TOKEN`
- `OVH_AI_ENDPOINTS_ACCESS_TOKEN`

Set them in **Repository → Settings → Secrets and variables → Actions**. Never put API keys in repository files.

## Primary sources

- Cloudflare Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare FLUX.1 schnell model and API schema: https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/
- OVHcloud free SDXL catalog, API examples, and rate limits: https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/stable-diffusion-xl/
- OVHcloud AI Endpoints capabilities and limits: https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-capabilities
- OVHcloud API key setup requirements: https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started
- Stability AI pricing and introductory credits: https://platform.stability.ai/pricing
- Hugging Face Inference Providers pricing: https://huggingface.co/docs/inference-providers/pricing
- Pollinations authentication and model discovery: https://github.com/pollinations/pollinations

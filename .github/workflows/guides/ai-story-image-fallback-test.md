# AI Story Image Fallback Test

## Purpose

This is a manual, isolated test of the AI Story image providers that run after the OVHcloud primary provider fails. It does not create a story, call Gemini, synthesize narration, render a video, send Telegram messages or modify topic history.

## Provider order

The workflow tests the fallback chain in this order and stops after the first provider returns a valid PNG:

1. **AI Horde** — anonymous generation.
2. **Vexa AI** — tries its HD route first, then its FLUX route.
3. **Pollinations** — final fallback.

The test deliberately starts at AI Horde, so it tests the fallback providers without spending time on the OVHcloud primary.

## How to run

1. Open GitHub → Actions → **AI Story Image Fallback Test**.
2. Select **Run workflow** on the `main` branch.
3. Keep the default prompt or enter a different image prompt.
4. Start the run and inspect the **Try AI Horde, then Vexa HD/FLUX, then Pollinations** step.
5. Open the run's Artifacts section and download `ai-story-image-fallback-test` to inspect the generated PNG.

The successful provider is printed in the job log. If all providers fail, the workflow fails and prints the individual provider errors.

## Runtime and output

- Runner: Ubuntu, Python 3.11.
- Timeout: 30 minutes (AI Horde can wait in a public generation queue).
- No Gemini, Cloudflare, Telegram or paid API secrets are required.
- Output: one validated PNG artifact, retained for 3 days.
- The workflow is read-only with respect to repository contents.

## Troubleshooting

- **AI Horde queue timeout/fault:** rerun later; anonymous worker availability varies.
- **Vexa HD and FLUX both fail:** inspect both route errors in the log; Vexa is treated as one fallback stage.
- **Pollinations fails:** inspect the HTTP or image-validation error; the workflow reports failure only after all three stages fail.
- A successful test proves that at least one provider worked at that time. It does not guarantee future availability or prove that every later fallback was exercised in that run.

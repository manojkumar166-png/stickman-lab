# SDXL 48-image Colab generator

Notebook: [Open the SDXL 48-image generator in Google Colab](https://colab.research.google.com/github/manojkumar166-png/stickman-lab/blob/main/science-channel/colab/sdxl_48_image_generator.ipynb)

## Workflow

1. Run **Actions → Science Channel — Daily Gemini Planner**.
2. Wait for the planner to commit the episode and send `image-prompts.md` to Telegram.
3. Open the Telegram document, copy its complete text, and open the Colab notebook above.
4. In Colab, choose **Runtime → Change runtime type → T4 GPU** if a GPU is offered.
5. Run the notebook cells from top to bottom. Paste the complete prompt document into the large **Prompts** box when asked.
6. The notebook checks for all 48 scene headings, downloads the public Stable Diffusion XL Base 1.0 and official Refiner 1.0 models, then generates and refines images one at a time at 1024×576 with 40 sampling steps. It saves each completed image so a restarted session can resume without regenerating saved scenes.
7. Download the resulting `science-channel-48-images.zip`. The notebook checks for exactly 48 WebP images and the existing importer's 25 MiB ZIP limit.
8. On GitHub `main`, upload the ZIP directly into `science-channel/telegram-uploads/` and commit it.
9. Open **Actions → Telegram ZIP Import → Run workflow**:
   - `episode_path`: copy the full episode folder path from the caption on the Telegram prompt document.
   - `zip_path`: `science-channel/telegram-uploads/science-channel-48-images.zip`
10. Run the importer. It validates and imports the 48 images; the existing Science Channel renderer then handles the video.

## Requirements and limitations

- No Gemini key, image API key, Cloudflare, GitHub token, or code editing is required in Colab.
- The notebook uses the public `stabilityai/stable-diffusion-xl-base-1.0` and `stabilityai/stable-diffusion-xl-refiner-1.0` models through Diffusers. The Base creates each scene and the Refiner processes its final denoising stage for additional detail.
- Google Colab must offer a GPU runtime. Free GPU access, runtime duration and availability are not guaranteed.
- Generation is sequential, not 48 images simultaneously. The Base + Refiner quality pass is slower and more memory-intensive; 48 images can take a long time and may exceed one free session. A T4 may run slowly or encounter memory/runtime limits.
- If a session disconnects, reconnect, rerun the install/GPU/model cells, paste the same prompt document, then rerun generation. Existing valid scene files in the Colab session are skipped; if the Colab runtime was fully reset, its temporary files may be lost and generation must start again.
- The ZIP must be no larger than 25 MiB because that is the current repository importer's enforced limit.
- Do not also send individual images to the Telegram image receiver for the same episode. Use either the ZIP import route or the Telegram receiver, not both.

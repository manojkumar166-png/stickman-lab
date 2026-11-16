# Original Stickman Skill on GitHub

This repository now tracks the complete upstream `michxlai/stickman-skill` project as a pinned Git submodule at `vendor/stickman-skill`. The submodule contains the original 2D engine, 3D engine, character rigs, motion/props/sets, production scripts, references, templates and CC0 SFX recordings.

Upstream revision pinned: `336608251fb16081b112e0742616baf46d0ca518`.

## Run it

1. Open **Actions → Cinematic Stickman Film (original skill engine)**.
2. Choose `original-2d` or `original-3d`.
3. Run once with `approve_preview = no`. Download and inspect the storyboard artifact.
4. If the storyboard is right, run again with `approve_preview = yes`. The job renders the MP4, runs the frame/audio audit, uploads the deliverables and commits the output to the selected branch.

Choose `existing-cinematic` to run the repository's previous custom Canvas/Playwright renderer instead.

## Edit the film

- `stickman-films/original-skill/film_2d.js`: editable film code for the original 2D engine.
- `stickman-films/original-skill/film_3d.js`: editable film code for the original 3D engine.
- `stickman-films/original-skill/audio_mix.py`: sound design settings. The starter enables real SFX, with music and voiceover off.

The current upstream starter films are examples: 2D is 12 seconds and 3D is 9 seconds. Their duration, cuts, shots, character poses, props, camera and sound events are authored in JavaScript/Python. Edit the relevant file to create a different story or length; the workflow copies it into the build workspace before rendering.

The original skill is a code-first production toolkit, not a hosted AI model. GitHub Actions does not invent a new screenplay from a text prompt by itself. This setup makes the complete animation/render pipeline run without paid APIs; story/shot code is authored in the checked-in film files.

## Free / no-key operation

The original engine runs locally on the GitHub-hosted runner using Python, Playwright/Chromium, FFmpeg and (for 3D) Three.js. Its bundled Kenney sound effects are CC0 as credited upstream. No Gemini, OpenAI, Claude, ElevenLabs, Cloudflare AI or other API key is used by this workflow. GitHub Actions runner minutes and artifact retention remain subject to GitHub's plan and repository settings.

## Output

The approved render is saved to `stickman-films/latest/video.mp4`, with the film metadata, contact sheet and FFprobe audit alongside it. The Actions artifact is retained for 30 days.

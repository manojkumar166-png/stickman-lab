#!/usr/bin/env python3
"""Build a self-contained HTML page with the rendered MP4 and storyboard."""

import html
import json
import pathlib

FILM_PATH = pathlib.Path("stickman-films/latest/film.json")
VIDEO_PATH = pathlib.Path("stickman-films/latest/video.mp4")
OUTPUT_PATH = pathlib.Path("stickman-films/latest/index.html")

def main():
    if not FILM_PATH.exists():
        raise SystemExit(f"Missing {FILM_PATH}; run generate_daily_stickman.py first.")
    film = json.loads(FILM_PATH.read_text(encoding="utf-8"))
    esc = lambda value: html.escape(str(value or ""))
    scene_cards = []
    for scene in film.get("scenes", []):
        scene_cards.append(
            "<section class='scene'>"
            f"<h2>Scene {int(scene.get('n', 0))}: {esc(scene.get('title'))} "
            f"<small>{esc(scene.get('start'))}–{esc(scene.get('end'))}s</small></h2>"
            f"<p><b>Camera:</b> {esc(scene.get('camera'))}</p>"
            f"<p>{esc(scene.get('action'))}</p></section>"
        )
    video = "<video controls playsinline preload='metadata' src='video.mp4'></video>" if VIDEO_PATH.exists() else "<p>MP4 not rendered yet.</p>"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(film.get('title'))} - Daily Stickman</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{font-family:system-ui,sans-serif;background:#1a1025;color:#fff;
padding:24px;max-width:1000px;margin:auto;line-height:1.55}}
h1{{color:#ff9a83;line-height:1.15}}video{{display:block;width:100%;aspect-ratio:16/9;background:#08060d;border-radius:16px}}
.card,.scene{{background:#2a1b3d;padding:18px;border-radius:16px;margin:12px 0}}
.scene{{background:#ffffff12}}small{{color:#c9b8d8;font-weight:400}}.meta{{color:#dbcce8}}
</style></head><body>
<h1>{esc(film.get('title'))}</h1><p>{esc(film.get('premise'))}</p>
<div class="card"><b>{esc(film.get('length'))} · {esc(film.get('style'))} · 1920×1080 · 30 FPS</b>
<p class="meta">Rendered illustrated 2D animation</p>{video}
<p>Hero: {esc(film.get('hero'))}</p><p>End card: {esc(film.get('end_card'))}</p></div>
<h2>Storyboard</h2>{''.join(scene_cards)}
</body></html>"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"Built player: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

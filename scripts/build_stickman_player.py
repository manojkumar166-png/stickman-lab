#!/usr/bin/env python3
"""Build a simple, self-contained HTML storyboard player from latest/film.json."""

import html
import json
import pathlib

FILM_PATH = pathlib.Path("stickman-films/latest/film.json")
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
            f"<p><b>Sound:</b> {esc(scene.get('sound'))}</p>"
            f"<p>{esc(scene.get('action'))}</p></section>"
        )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(film.get('title'))} - Daily Stickman</title>
<style>
:root{{color-scheme:dark}}body{{font-family:system-ui,sans-serif;background:#1a1025;color:#fff;
padding:24px;max-width:820px;margin:auto;line-height:1.55}}
h1{{color:#ff8a7a;line-height:1.15}}.card,.scene{{background:#2a1b3d;padding:18px;
border-radius:16px;margin:12px 0}}.scene{{background:#ffffff12}}
small{{color:#c9b8d8;font-weight:400}}.meta{{color:#dbcce8}}
</style></head><body>
<h1>{esc(film.get('title'))}</h1><p>{esc(film.get('premise'))}</p>
<div class="card"><b>{esc(film.get('length'))} · {esc(film.get('style'))}</b>
<p class="meta">No voiceover · No background music · Sound effects only</p>
<p>Hero: {esc(film.get('hero'))}</p><p>End card: {esc(film.get('end_card'))}</p></div>
{''.join(scene_cards)}
<p class="meta">Storyboard generated automatically. Use these scene directions with your animation/rendering pipeline.</p>
</body></html>"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"Built player: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()

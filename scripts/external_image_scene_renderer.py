"""Render consistent, static SVG stickman science scenes for the storybook video."""
from __future__ import annotations
import html
import re
from pathlib import Path
from playwright.async_api import async_playwright

def _esc(value):
    return html.escape(" ".join(str(value or "").split()), quote=True)

def _wrap(text, limit=64, max_lines=2):
    words = str(text or "").split()
    lines, line = [], ""
    for word in words:
        if line and len(line) + len(word) + 1 > limit:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        lines.append(line)
    return lines[:max_lines]

def _illustration(scene, index):
    text = " ".join(str(scene.get(k, "")) for k in ("title", "visual", "narration", "background")).lower()
    # Scene-aware SVG motifs. All shapes are deterministic vector art, not generated images.
    if any(k in text for k in ("space", "planet", "orbit", "solar", "moon", "star", "galaxy", "black hole")):
        objects = '<circle cx="770" cy="315" r="92" fill="#5ba7e8" stroke="#17212b" stroke-width="9"/><ellipse cx="770" cy="315" rx="145" ry="42" fill="none" stroke="#17212b" stroke-width="9" transform="rotate(-18 770 315)"/><circle cx="990" cy="210" r="28" fill="#f8ce55" stroke="#17212b" stroke-width="7"/><circle cx="925" cy="455" r="15" fill="#f8ce55" stroke="#17212b" stroke-width="6"/>'
    elif any(k in text for k in ("cell", "bacteria", "microbe", "dna", "molecule", "atom", "protein")):
        objects = '<ellipse cx="790" cy="320" rx="150" ry="105" fill="#b7e4c7" stroke="#17212b" stroke-width="9"/><ellipse cx="790" cy="320" rx="50" ry="38" fill="#72b7a1" stroke="#17212b" stroke-width="7"/><circle cx="700" cy="290" r="15" fill="#f8ce55" stroke="#17212b" stroke-width="5"/><circle cx="860" cy="360" r="18" fill="#ee8f77" stroke="#17212b" stroke-width="5"/><path d="M710 355 Q750 390 765 365 T830 280" fill="none" stroke="#4776c5" stroke-width="8" stroke-linecap="round"/>'
    elif any(k in text for k in ("water", "ocean", "wave", "rain", "evapor", "cloud", "ice", "weather")):
        objects = '<path d="M620 365 Q700 300 780 365 T940 365 T1100 365" fill="none" stroke="#287db4" stroke-width="15" stroke-linecap="round"/><path d="M620 415 Q700 350 780 415 T940 415 T1100 415" fill="none" stroke="#62b8df" stroke-width="15" stroke-linecap="round"/><path d="M770 235 C720 290 740 315 770 315 C800 315 820 285 770 235Z" fill="#62b8df" stroke="#17212b" stroke-width="7"/><path d="M900 220 C850 275 870 300 900 300 C930 300 950 270 900 220Z" fill="#62b8df" stroke="#17212b" stroke-width="7"/>'
    elif any(k in text for k in ("electric", "circuit", "magnet", "energy", "electron", "current", "lightning")):
        objects = '<path d="M790 200 L720 330 L790 330 L735 455 L890 290 L810 290 L870 200Z" fill="#f8ce55" stroke="#17212b" stroke-width="9" stroke-linejoin="round"/><circle cx="970" cy="275" r="38" fill="#ee8f77" stroke="#17212b" stroke-width="8"/><path d="M950 275 H990 M970 255 V295" stroke="#17212b" stroke-width="7" stroke-linecap="round"/>'
    elif any(k in text for k in ("plant", "tree", "forest", "photosynthesis", "leaf", "flower")):
        objects = '<path d="M810 430 V285" stroke="#39754c" stroke-width="18" stroke-linecap="round"/><path d="M810 340 Q700 325 700 240 Q790 240 810 340Z" fill="#69b86e" stroke="#17212b" stroke-width="8"/><path d="M810 315 Q900 300 925 215 Q840 215 810 315Z" fill="#89cb75" stroke="#17212b" stroke-width="8"/><path d="M810 430 Q750 450 700 440 M810 430 Q870 455 930 440" fill="none" stroke="#39754c" stroke-width="9" stroke-linecap="round"/>'
    elif any(k in text for k in ("brain", "memory", "neuron", "nerve", "body", "heart", "blood", "lung", "human")):
        objects = '<path d="M790 250 C735 190 670 245 700 290 C655 340 710 390 755 365 C785 405 835 380 830 345 C885 320 855 260 820 265 C820 230 800 220 790 250Z" fill="#ee9b9b" stroke="#17212b" stroke-width="8"/><path d="M785 250 V365 M730 275 Q765 295 745 325 M820 280 Q790 300 820 320" fill="none" stroke="#a64f63" stroke-width="6"/>'
    else:
        objects = '<rect x="690" y="220" width="330" height="230" rx="22" fill="#e8f1ff" stroke="#17212b" stroke-width="9"/><path d="M735 385 L805 300 L860 345 L965 255" fill="none" stroke="#287db4" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/><circle cx="805" cy="300" r="13" fill="#f8ce55" stroke="#17212b" stroke-width="5"/><circle cx="965" cy="255" r="13" fill="#ee8f77" stroke="#17212b" stroke-width="5"/>'
    # A friendly stick figure points toward the scene-specific science motif.
    return f"""
    <svg viewBox="0 0 1280 720" width="1280" height="720" xmlns="http://www.w3.org/2000/svg" aria-label="Science illustration">
      <rect width="1280" height="720" fill="#fffdf7"/>
      <circle cx="965" cy="330" r="245" fill="#eaf4ff"/>
      <path d="M70 560 H1210" stroke="#d6e1eb" stroke-width="5" stroke-linecap="round"/>
      {objects}
      <g stroke="#17212b" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" fill="none">
        <circle cx="350" cy="300" r="58" fill="#ffd6a5"/>
        <path d="M305 286 Q350 225 395 286" stroke-width="17"/>
        <path d="M330 305 L332 307 M370 305 L372 307" stroke-width="8"/>
        <path d="M337 330 Q350 342 366 329" stroke-width="7"/>
        <path d="M350 360 L350 470"/>
        <path d="M350 390 L440 330 L500 340"/>
        <path d="M350 395 L300 445"/>
        <path d="M350 470 L300 555 M350 470 L405 555"/>
      </g>
      <path d="M440 330 L475 330" stroke="#17212b" stroke-width="13" stroke-linecap="round"/>
      <path d="M455 317 L477 330 L455 343" fill="none" stroke="#17212b" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="1050" cy="150" r="9" fill="#f8ce55"/><circle cx="1090" cy="180" r="6" fill="#ee8f77"/><path d="M610 180 l10 22 22 10 -22 10 -10 22 -10 -22 -22 -10 22 -10Z" fill="#f8ce55"/>
    </svg>"""

async def render_external_scenes(story: dict, scene_dir: Path, width: int, height: int):
    scenes = story.get("scenes") or []
    if not scenes:
        raise RuntimeError("No story scenes to render.")
    scene_dir.mkdir(parents=True, exist_ok=True)
    rendered = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        for i, scene in enumerate(scenes, start=1):
            title = _esc(scene.get("title") or story.get("topic") or "Science")
            caption = _esc(scene.get("narration") or scene.get("visual") or "")
            title_lines = _wrap(scene.get("title") or story.get("topic") or "Science", 42, 1)
            title_svg = _esc(title_lines[0] if title_lines else "Science")
            art = _illustration(scene, i)
            doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden}}
body{{font-family:Arial,Helvetica,sans-serif;background:#fffdf7}}
.top{{height:105px;background:#2463a6;border-bottom:7px solid #17212b;color:white;display:flex;align-items:center;padding:0 54px;font-size:37px;font-weight:900;letter-spacing:.3px}}
.art{{position:absolute;left:0;top:105px;width:100%;height:515px;overflow:hidden}}
.art svg{{width:100%;height:100%}}
.caption{{position:absolute;left:0;bottom:0;width:100%;height:105px;background:#fffdf7;border-top:6px solid #17212b;display:flex;align-items:center;justify-content:center;padding:12px 58px;text-align:center;font-size:25px;line-height:1.15;font-weight:800;color:#17212b}}
.index{{position:absolute;right:22px;top:37px;font-size:17px;font-weight:800;color:#dcecff}}
</style></head><body><div class="top">{title_svg}</div><div class="index">{i:02d} / {len(scenes):02d}</div><div class="art">{art}</div><div class="caption">{caption[:210]}</div></body></html>"""
            await page.set_content(doc, wait_until="load")
            path = scene_dir / f"scene-{i:03d}.png"
            await page.screenshot(path=str(path), type="png")
            rendered.append(path)
        await browser.close()
    return rendered

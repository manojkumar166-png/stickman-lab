"""Compose AI-generated stills with a polished HTML/CSS presentation layer."""
from __future__ import annotations
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:1280px;height:720px;overflow:hidden;background:#101b25}
.scene{position:relative;width:1280px;height:720px;overflow:hidden;background:#172b3a;color:#fff}
.art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(10,20,29,.64),rgba(10,20,29,.10) 70%),linear-gradient(0deg,rgba(9,18,26,.46),transparent 42%)}
.grain{position:absolute;inset:0;opacity:.11;pointer-events:none;background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.86' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.3'/%3E%3C/svg%3E")}
.top{position:absolute;left:58px;top:42px;display:flex;gap:12px;align-items:center;font:600 15px/1.2 system-ui,sans-serif;letter-spacing:2.8px;text-transform:uppercase;color:#fff5d9;text-shadow:0 2px 12px #14212b}
.dot{width:8px;height:8px;border-radius:50%;background:#f1c987;box-shadow:0 0 18px #f1c987}
.title{position:absolute;left:58px;bottom:64px;width:760px;font:600 43px/1.13 Georgia,'Times New Roman',serif;letter-spacing:-.5px;text-shadow:0 3px 20px rgba(0,0,0,.65)}
.index{position:absolute;right:58px;bottom:68px;font:500 13px/1 system-ui,sans-serif;letter-spacing:2px;color:#fff3d3}
.rule{position:absolute;left:58px;bottom:42px;width:90px;height:2px;background:#f1c987}
</style></head><body><main class="scene"><img class="art" src="IMAGE_DATA"><div class="shade"></div><div class="grain"></div><div class="top"><span class="dot"></span><span>SCIENCE • A VISUAL STORY</span></div><div class="title">SCENE_TITLE</div><div class="index">SCENE_INDEX</div><div class="rule"></div></main></body></html>"""

async def compose(image_paths: list[Path], story: dict, output_dir: Path, width: int, height: int):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required for image encoding.") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = story.get("scenes", [])
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        for i, image_path in enumerate(image_paths):
            with Image.open(image_path) as im:
                im = im.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
                import io, base64
                buf = io.BytesIO(); im.save(buf, format="JPEG", quality=94)
                data = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            scene = scenes[i] if i < len(scenes) else {}
            title = str(scene.get("title") or scene.get("visual_description") or scene.get("narration") or story.get("topic") or "A Science Discovery")
            title = " ".join(title.split())[:95].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html = HTML.replace("IMAGE_DATA", data).replace("SCENE_TITLE", title).replace("SCENE_INDEX", f"{i+1:02d} / {len(image_paths):02d}")
            await page.set_content(html, wait_until="load")
            await page.screenshot(path=str(output_dir / f"scene-{i:03d}.png"), type="png")
        await browser.close()

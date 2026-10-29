"""Render downloaded public-domain illustrations as static, subtitle-bearing scenes."""
from __future__ import annotations
import base64
import html
import mimetypes
from pathlib import Path
from playwright.async_api import async_playwright

def _escape(value):
    return html.escape(" ".join(str(value or "").split()), quote=True)

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
            source = Path(str(scene.get("_external_image_path") or ""))
            data_uri = ""
            if source.is_file():
                mime = mimetypes.guess_type(source.name)[0] or "image/jpeg"
                data_uri = "data:" + mime + ";base64," + base64.b64encode(source.read_bytes()).decode("ascii")
            image_html = f'<img src="{data_uri}">' if data_uri else ""
            title = _escape(story.get("topic") or scene.get("title") or "Science")
            caption = _escape(scene.get("narration") or scene.get("visual_description") or "")
            doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden}}
main{{position:relative;width:100%;height:100%;background:linear-gradient(135deg,#172e55,#236b78 52%,#f0a45b);font-family:system-ui,sans-serif}}
img{{position:absolute;inset:7% 5% 18%;width:90%;height:75%;object-fit:contain;filter:drop-shadow(0 12px 20px #0006)}}
.shade{{position:absolute;inset:0;background:linear-gradient(180deg,#07152766,transparent 26%,transparent 58%,#061323dd);}}
.kicker{{position:absolute;left:4%;top:3%;font-size:15px;font-weight:900;letter-spacing:3px;color:white;text-shadow:0 2px 5px #000}}
.title{{position:absolute;left:4%;top:7%;width:92%;font-size:32px;line-height:1.08;font-weight:950;color:#ffe94d;text-transform:uppercase;text-shadow:2px 2px #111,-2px -2px #111,2px -2px #111,-2px 2px #111,0 5px 12px #000}}
.caption{{position:absolute;left:5%;bottom:6%;width:90%;font-size:27px;line-height:1.18;font-weight:900;text-align:center;color:white;text-shadow:2px 2px #111,-2px -2px #111,2px -2px #111,-2px 2px #111,0 4px 9px #000}}
.index{{position:absolute;right:4%;top:3%;font-size:13px;font-weight:800;color:white;text-shadow:0 2px 5px #000}}
</style></head><body><main>{image_html}<div class="shade"></div><div class="kicker">SCIENCE SHORT</div><div class="title">{title}</div><div class="caption">{caption[:170]}</div><div class="index">{i:02d} / {len(scenes):02d}</div></main></body></html>"""
            await page.set_content(doc, wait_until="load")
            path = scene_dir / f"scene-{i:03d}.png"
            await page.screenshot(path=str(path), type="png")
            rendered.append(path)
        await browser.close()
    return rendered

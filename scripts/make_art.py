import os, random, hashlib, asyncio, aiohttp, io, urllib.parse, base64, time, requests
from PIL import Image, ImageDraw, ImageFont
from scripts.make_art_python import make_scene_art as make_scene_art_python

STYLE = ("flat 2D vector illustration, educational explainer style, clean bold outlines, "
         "solid flat colors, limited bright palette, simple geometric shapes, "
         "plain light background, no gradients, no text, no photorealism")

PALETTES = {
 "sky":("#A7D8FF","#F5FCFF"), "lab":("#D9F2F0","#F8FFFD"),
 "space":("#101B3B","#253D70"), "ocean":("#56C5E8","#DDF8FF"),
 "forest":("#9ED69A","#E8F5C8"), "city":("#F7C98B","#FFF1D5"),
 "home":("#F4D9B7","#FFF6E8"), "cave":("#8D8A9A","#D6D0D9"),
 "desert":("#F4C477","#FFE8B0"), "mountain":("#B8D8E8","#F4FBFF")
}

def font(size, bold=False):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def build_prompt(visual):
    clean = " ".join(visual.split()).replace('"', "")[:250]
    return f"{clean}, {STYLE}"

# --- CLOUDFLARE CREDENTIALS ---
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")

# --- EXPENSIVE MODEL (For Style Anchor only) ---
CF_URL_EXPENSIVE = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"

def generate_style_anchor():
    print("Generating 1 style anchor image with expensive model...")
    prompt = f"A cute stickman pointing at a science diagram. {STYLE}"
    r = requests.post(CF_URL_EXPENSIVE, headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
                      json={"prompt": prompt, "steps": 4}, timeout=90)
    r.raise_for_status()
    return base64.b64decode(r.json()["result"]["image"])

# --- CHEAP MODEL (For all 47 scenes) ---
CF_URL_CHEAP = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"

def cf_image_cheap(prompt, ref_png=None):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("CF credentials missing")
    
    form_data = {
        "prompt": (None, prompt),
        "width": (None, "1024"),
        "height": (None, "576")
    }
    
    if ref_png:
        # Pass the style anchor to the cheap model
        form_data["input_image_0"] = ("style.png", ref_png, "image/png")
    
    r = requests.post(CF_URL_CHEAP, headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
                      files=form_data, timeout=120)
    r.raise_for_status()
    
    if r.headers.get("content-type", "").startswith("image/"):
        return r.content
        
    j = r.json()
    return base64.b64decode(j.get("result", j)["image"])

async def generate_all_ai_images(scenes, out_dir, width, height):
    print("Generating AI illustrations (Style Anchor + Cheap Model)...")
    results = []
    
    # 1. Generate the style anchor once
    try:
        style_anchor = generate_style_anchor()
    except Exception as e:
        print(f"Failed to generate style anchor: {e}")
        style_anchor = None

    # 2. Generate all 47 scenes using the cheap model + style anchor
    for i, scene in enumerate(scenes, 1):
        visual = scene.get("visual", "science illustration")
        prompt = build_prompt(visual)
        
        try:
            img_data = cf_image_cheap(prompt, ref_png=style_anchor)
            results.append((i, img_data))
            print(f"  Scene {i}/{len(scenes)}: Klein OK")
        except Exception as e:
            print(f"  Klein failed at scene {i}: {e}")
            results.append((i, None))
            
        if i < len(scenes):
            time.sleep(6)
            
    return results

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    if ai_image_data:
        try:
            im = Image.open(io.BytesIO(ai_image_data)).convert("RGB")
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error processing image for scene {idx}: {e}")
            ai_image_data = None

    if not ai_image_data:
        return make_scene_art_python(scene, idx, total, path, width, height)

    d = ImageDraw.Draw(im)

    # Title bar
    title = (scene.get("title") or "Science Discovery")[:58]
    d.rounded_rectangle((30, 20, width - 30, 90), radius=15, fill="#2A5CAA")
    d.text((50, 40), title, font=font(28, True), fill="white")

    # Caption bar
    narration = scene.get("narration", "")
    words = narration.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) < 75:
            current_line += word + " "
        else:
            lines.append(current_line.strip())
            current_line = word + " "
    if current_line:
        lines.append(current_line.strip())
    lines = lines[:2]
    if len(lines) == 2 and len(narration) > 140:
         lines[1] += "..."

    d.rectangle((0, height - 110, width, height), fill="black")
    y_offset = height - 90
    for line in lines:
        d.text((40, y_offset), line, font=font(24, False), fill="white")
        y_offset += 35

    im.save(path, quality=95)
    return path
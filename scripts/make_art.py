import os, random, hashlib, asyncio, aiohttp, io, urllib.parse, base64, time, requests
from PIL import Image, ImageDraw, ImageFont
from scripts.make_art_python import make_scene_art as make_scene_art_python

STYLE = ("flat 2D vector illustration, educational explainer style, clean bold outlines, "
         "solid flat colors, limited bright palette, simple geometric shapes, "
         "plain light background, no gradients, no text, no photorealism")

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

# --- CHEAP MODEL ONLY: FLUX-2-KLEIN-4B ---
CF_URL_CHEAP = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"

def cf_image_cheap(prompt):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("CF credentials missing")
    
    form_data = {
        "prompt": (None, prompt),
        "width": (None, "1024"),
        "height": (None, "576")
    }
    
    r = requests.post(CF_URL_CHEAP, headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
                      files=form_data, timeout=120)
    r.raise_for_status()
    
    if r.headers.get("content-type", "").startswith("image/"):
        return r.content
        
    j = r.json()
    return base64.b64decode(j.get("result", j)["image"])

async def generate_all_ai_images(scenes, out_dir, width, height):
    print("Generating AI illustrations (Cheap Model ONLY)...")
    results = []
    
    for i, scene in enumerate(scenes, 1):
        visual = scene.get("visual", "science illustration")
        prompt = build_prompt(visual)
        
        try:
            img_data = cf_image_cheap(prompt)
            results.append((i, img_data))
            print(f"  Scene {i}/{len(scenes)}: Klein OK")
        except Exception as e:
            print(f"  Klein failed at scene {i}: {e}")
            results.append((i, None))
            
        if i < len(scenes):
            time.sleep(6)
            
    # If any failed, reuse a successful image to fill the gap
    successful_images = [img for idx, img in results if img is not None]
    
    if not successful_images:
        print("  All images failed. Falling back to stickmen.")
        return results
        
    final_results = []
    for i, img_data in results:
        if img_data is not None:
            final_results.append((i, img_data))
        else:
            random_img = random.choice(successful_images)
            final_results.append((i, random_img))
            print(f"  Scene {i}/{len(scenes)}: Filled with a random AI image")
            
    return final_results

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
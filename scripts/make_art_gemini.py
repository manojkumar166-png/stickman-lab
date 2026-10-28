import os, base64, time, random, io, requests
from PIL import Image, ImageDraw, ImageFont
from scripts.make_art_python import make_scene_art as make_scene_art_python

STYLE = ("Flat 2D vector illustration, educational explainer comic style. "
         "Clean uniform dark-navy outlines, solid flat color fills, no gradients, "
         "no shadows, no textures, no text or letters. "
         "Palette: teal, warm yellow, coral, soft purple on a pale cream background. "
         "16:9 landscape, main subject centered with open space around it.")

# --- GEMINI PROVIDER ---
def gemini_image(prompt):
    api_key = os.getenv("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={api_key}"
    r = requests.post(url, json={"contents":[{"parts":[{"text": prompt}]}]}, timeout=90)
    r.raise_for_status()
    data = r.json()
    for part in data["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return base64.b64decode(part["inlineData"]["data"])
    raise RuntimeError("No image in Gemini response")

# --- CLOUDFLARE PROVIDER ---
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CF_API_TOKEN")
CF_URL = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"

def cf_image(prompt):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("CF credentials missing")
    r = requests.post(CF_URL, headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
                      json={"prompt": prompt, "steps": 4}, timeout=90)
    r.raise_for_status()
    return base64.b64decode(r.json()["result"]["image"])

async def generate_all_ai_images(scenes, out_dir, width, height):
    print("Generating AI illustrations (Gemini First, then Cloudflare)...")
    
    results = {}
    provider_name = "Gemini"
    provider_fn = gemini_image
    
    for i, scene in enumerate(scenes, 1):
        visual = scene.get("visual", "science illustration")
        prompt = f"{visual}. {STYLE}"
        
        try:
            img_data = provider_fn(prompt)
            results[i] = img_data
            print(f"  Scene {i}/{len(scenes)}: {provider_name} OK")
        except Exception as e:
            print(f"  Scene {i} failed: {e}")
            # If Gemini fails, switch to Cloudflare for the rest
            if provider_name == "Gemini":
                print("  Switching to Cloudflare for remaining scenes...")
                provider_name = "Cloudflare"
                provider_fn = cf_image
                try:
                    img_data = provider_fn(prompt)
                    results[i] = img_data
                    print(f"  Scene {i}/{len(scenes)}: {provider_name} OK")
                except Exception as e2:
                    print(f"  Cloudflare failed too. Falling back to stickman for scene {i}.")
                    results[i] = None
            else:
                results[i] = None
        
        # Pacing: 7s for Gemini, 6s for Cloudflare
        if i < len(scenes):
            time.sleep(7 if provider_name == "Gemini" else 6)
            
    return results

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    if ai_image_data:
        try:
            im = Image.open(io.BytesIO(ai_image_data)).convert("RGB")
            im = im.resize((width, height), Image.Resampling.LANCZOS)
            
            # Draw Title & Caption
            d = ImageDraw.Draw(im)
            title = (scene.get("title") or "Science Discovery")[:58]
            d.rounded_rectangle((30, 20, width - 30, 90), radius=15, fill="#2A5CAA")
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            except:
                font = ImageFont.load_default()
            d.text((50, 40), title, font=font, fill="white")

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
            if current_line: lines.append(current_line.strip())
            lines = lines[:2]
            
            d.rectangle((0, height - 110, width, height), fill="black")
            y_offset = height - 90
            try:
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            except:
                font_small = ImageFont.load_default()
            for line in lines:
                d.text((40, y_offset), line, font=font_small, fill="white")
                y_offset += 35

            im.save(path, quality=95)
            return path
        except Exception as e:
            print(f"Error processing image {idx}: {e}")
            ai_image_data = None

    # Fallback
    return make_scene_art_python(scene, idx, total, path, width, height)
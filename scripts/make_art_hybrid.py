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
    print("Generating Hybrid AI illustrations...")
    
    # Claude's Trick: Generate 1 image for every 2 scenes
    # We still need a full list of images for the renderer, but we only fetch half.
    total_images = len(scenes)
    results = {}
    
    # We will try Gemini first
    provider_name = "Gemini"
    provider_fn = gemini_image
    
    for i in range(1, total_images + 1, 2): # Skip by 2
        # Combine the visual descriptions of the current and next scene
        v1 = scenes[i-1].get("visual", "science illustration")
        v2 = scenes[i].get("visual", v1) if i < total_images else v1
        combined_visual = f"{v1}. {v2}"
        
        prompt = f"{combined_visual}. {STYLE}"
        
        try:
            img_data = provider_fn(prompt)
            results[i] = img_data
            results[i+1] = img_data # Reuse the same image for the next scene!
            print(f"  Image {i}-{min(i+1, total_images)}/{total_images}: {provider_name} OK")
        except Exception as e:
            print(f"  Failed image {i}: {e}")
            # If Gemini fails, switch to Cloudflare for everything remaining
            if provider_name == "Gemini":
                print("  Switching to Cloudflare...")
                provider_name = "Cloudflare"
                provider_fn = cf_image
                # Try again with Cloudflare
                try:
                    img_data = provider_fn(prompt)
                    results[i] = img_data
                    results[i+1] = img_data
                    print(f"  Image {i}-{min(i+1, total_images)}/{total_images}: {provider_name} OK")
                except Exception as e2:
                    print(f"  Cloudflare failed too. Falling back to stickmen.")
                    results[i] = None
                    results[i+1] = None
            else:
                results[i] = None
                results[i+1] = None
        
        # Pacing
        time.sleep(7 if provider_name == "Gemini" else 6)
        
    return results

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    if ai_image_data:
        try:
            im = Image.open(io.BytesIO(ai_image_data)).convert("RGB")
            im = im.resize((width, height), Image.Resampling.LANCZOS)
            # Draw the title & caption
            d = ImageDraw.Draw(im)
            title = (scene.get("title") or "Science Discovery")[:58]
            d.rounded_rectangle((30, 20, width - 30, 90), radius=15, fill="#2A5CAA")
            d.text((50, 40), title, font=ImageFont.load_default(), fill="white") # Fallback font
            im.save(path, quality=95)
            return path
        except Exception as e:
            print(f"Error processing image {idx}: {e}")
            ai_image_data = None

    # Fallback
    return make_scene_art_python(scene, idx, total, path, width, height)
import os, random, hashlib, asyncio, aiohttp, io, urllib.parse, time
from PIL import Image, ImageDraw, ImageFont

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

async def fetch_ai_image(session, prompt, seed):
    url = f"https://image.pollinations.ai/prompt/{prompt}?width=1280&height=720&nologo=true&seed={seed}&model=flux"
    async with session.get(url, timeout=120) as response:
        response.raise_for_status()
        return await response.read()

async def generate_all_ai_images(scenes, out_dir, width, height):
    print("Generating AI illustrations (This will take ~12 minutes to avoid rate limits)...")
    async with aiohttp.ClientSession() as session:
        results = []
        for i, scene in enumerate(scenes, 1):
            visual = scene.get("visual", "science illustration")
            # Force the 2D vector comic style
            prompt = urllib.parse.quote(f"2D flat vector illustration, colorful, educational comic style, clean bold outlines, simple background, cute character, {visual}")
            seed = int(hashlib.sha256((visual+str(i)).encode()).hexdigest()[:8],16)
            try:
                img_data = await fetch_ai_image(session, prompt, seed)
                results.append((i, img_data))
                print(f"  Downloaded scene {i}/{len(scenes)}...")
            except Exception as e:
                print(f"  Failed scene {i}: {e}")
                results.append((i, None))
            
            # WAIT 15 SECONDS TO PREVENT RATE LIMITS
            if i < len(scenes):
                await asyncio.sleep(15)
                
        return results

def make_scene_art(scene, idx, total, path, width=1280, height=720, ai_image_data=None):
    if ai_image_data:
        try:
            im = Image.open(io.BytesIO(ai_image_data)).convert("RGB")
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error processing AI image for scene {idx}: {e}")
            ai_image_data = None

    if not ai_image_data:
        # Fallback to simple background if AI fails
        bg = scene.get("background","sky").lower()
        top,bottom = PALETTES.get(bg, PALETTES["sky"])
        im = Image.new("RGB",(width,height),top)
        d = ImageDraw.Draw(im)
        for y in range(height):
            t=y/height
            import PIL.ImageColor as IC
            a,b=IC.getrgb(top),IC.getrgb(bottom)
            col=tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
            d.line((0,y,width,y),fill=col)

    d = ImageDraw.Draw(im)
    
    # 1. Draw the Top Title Bar (Vibrant blue)
    title = (scene.get("title") or "Science Discovery")[:58]
    d.rounded_rectangle((30, 20, width - 30, 90), radius=15, fill="#2A5CAA")
    d.text((50, 40), title, font=font(28, True), fill="white")

    # 2. Draw the Scene Counter in the top right
    d.text((width - 180, 42), f"Scene {idx}/{total}", font=font(20, True), fill="white")

    # 3. Draw the Bottom Caption Bar
    narration = scene.get("narration", "")
    # Wrap text
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
    
    lines = lines[:2] # Only show first 2 lines
    if len(lines) == 2 and len(narration) > 140:
         lines[1] += "..."

    # Draw black box
    d.rectangle((0, height - 110, width, height), fill="black")
    
    # Draw text inside box
    y_offset = height - 90
    for line in lines:
        d.text((40, y_offset), line, font=font(24, False), fill="white")
        y_offset += 35

    im.save(path, quality=95)
    return path
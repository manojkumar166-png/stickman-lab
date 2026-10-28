import os, random, hashlib, asyncio, aiohttp, io, urllib.parse
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
    url = url = f"https://image.pollinations.ai/prompt/{prompt}?width=1280&height=720&nologo=true&seed={seed}&model=flux&key=sk_RspT3lJVIzCYWNdvdh4Mlmyw5qGklFQI"

async def generate_all_ai_images(scenes, out_dir, width, height):
    print("Generating AI illustrations (this takes a few minutes)...")
    async with aiohttp.ClientSession() as session:
        results = []
        for i, scene in enumerate(scenes, 1):
            visual = scene.get("visual", "science illustration")
            prompt = urllib.parse.quote(f"2d cartoon style, colorful, educational, high quality, flat colors, {visual}")
            seed = int(hashlib.sha256((visual+str(i)).encode()).hexdigest()[:8],16)
            try:
                img_data = await fetch_ai_image(session, prompt, seed)
                results.append((i, img_data))
                print(f"  Downloaded scene {i}/{len(scenes)}...")
            except Exception as e:
                print(f"  Failed scene {i}: {e}")
                results.append((i, None))
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
        bg = scene.get("background","sky").lower()
        top,bottom = PALETTES.get(bg, PALETTES["sky"])
        im = Image.new("RGB",(width,height),top)
        d = ImageDraw.Draw(im)
        import PIL.ImageColor as IC
        a,b=IC.getrgb(top),IC.getrgb(bottom)
        for y in range(height):
            t=y/height
            col=tuple(int(a[c]*(1-t)+b[c]*t) for c in range(3))
            d.line((0,y,width,y),fill=col)
        ground_y=int(height*.78)
        if bg in ("sky","city","desert","mountain","forest","home","lab"):
            d.rectangle((0,ground_y,width,height), fill={"sky":"#7CCB79","city":"#D6B17A","desert":"#E5B45E","mountain":"#B5D0A1","forest":"#5EAA68","home":"#D7B68F","lab":"#C5E2DF"}.get(bg,"#7CCB79"))
        cx=int(width*.38); cy=int(height*.65); head=48
        skin=random.choice(["#FFD7B0","#F4C9A6","#E8B58F"])
        shirt=random.choice(["#F15B5B","#3979D8","#F2B544","#6C56B8","#24A08B"])
        d.ellipse((cx-55,ground_y-10,cx+55,ground_y+12),fill="#66877A")
        d.line((cx,cy+70,cx-30,cy+130),fill="#252A35",width=12)
        d.line((cx,cy+70,cx+32,cy+130),fill="#252A35",width=12)
        d.line((cx,cy+10,cx,cy+75),fill=shirt,width=22)
        action=scene.get("action","explain").lower()
        if action in ("point","explain","observe"):
            d.line((cx,cy+25,cx+65,cy-5),fill="#252A35",width=10)
            d.ellipse((cx+58,cy-14,cx+76,cy+4),fill=skin,outline="#252A35",width=2)
        else:
            d.line((cx,cy+25,cx-45,cy-20),fill="#252A35",width=10)
            d.line((cx,cy+25,cx+45,cy-20),fill="#252A35",width=10)
        d.ellipse((cx-head,cy-head*2,cx+head,cy),fill=skin,outline="#252A35",width=5)
        d.ellipse((cx-20,cy-63,cx-10,cy-53),fill="#20242B")
        d.ellipse((cx+10,cy-63,cx+20,cy-53),fill="#20242B")
        d.arc((cx-18,cy-50,cx+18,cy-25),0,180,fill="#7A3D37",width=3)

    d = ImageDraw.Draw(im)
    title = (scene.get("title") or "Science discovery")[:58]
    overlay = Image.new("RGBA", im.size, (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((40,35,width-40,112),radius=20,fill=(255,255,255,230),outline="#26364A",width=3)
    im.paste(overlay, (0,0), overlay)
    d.text((65,53), title, font=font(30, True), fill="#253247")
    d.rounded_rectangle((40,height-70,300,height-28),radius=12,fill="#FFFFFF")
    d.text((55,height-62), f"SCIENCE • SCENE {idx}/{total}", font=font(16, True), fill="#34445A")
    im.save(path, quality=95)
    return path
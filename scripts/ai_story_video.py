#!/usr/bin/env python3
"""Gemini-planned science documentaries and animated stories rendered from generated stills."""
import argparse, asyncio, base64, io, json, os, re, subprocess, sys, time
from pathlib import Path
import edge_tts, requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"ai-story-video-output"
KEY=os.getenv("GEMINI_API_KEY","").strip()
MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash").strip()
FALLBACK=[x.strip() for x in os.getenv("GEMINI_FALLBACK_MODELS","gemini-2.5-flash-lite,gemini-2.0-flash").split(",") if x.strip()]
TIMEOUT=(20,180)

def parse_json(raw):
    fence=chr(96)*3
    raw=raw.strip()
    if raw.startswith(fence):
        raw=raw.split("\n",1)[-1]
        if raw.endswith(fence): raw=raw[:-3]
    start=raw.find("{")
    if start<0: raise ValueError("Gemini returned no JSON object")
    depth=0; quoted=False; escaped=False
    for i,ch in enumerate(raw[start:],start):
        if quoted:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': quoted=False
        elif ch=='"': quoted=True
        elif ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0: return json.loads(raw[start:i+1])
    raise ValueError("Gemini returned incomplete JSON")

def gemini(prompt):
    if not KEY: raise RuntimeError("Add GEMINI_API_KEY in repository Actions secrets.")
    errors=[]
    for model in dict.fromkeys([MODEL]+FALLBACK):
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                r=requests.post(url,params={"key":KEY},json={"contents":[{"parts":[{"text":prompt}]}],
                    "generationConfig":{"responseMimeType":"application/json","temperature":0.8}},timeout=90)
                if r.status_code in (400,403,404,408,429,500,502,503,504):
                    raise RuntimeError(f"Gemini {model} HTTP {r.status_code}: {r.text[:700]}")
                r.raise_for_status()
                candidates=r.json().get("candidates") or []
                parts=candidates[0].get("content",{}).get("parts",[]) if candidates else []
                result=parse_json("".join(p.get("text","") for p in parts if isinstance(p,dict)))
                print(f"Gemini planner active: {model}",flush=True)
                return result
            except Exception as e:
                errors.append(f"{model} try {attempt+1}: {e}")
                if attempt==0: time.sleep(3)
    raise RuntimeError("All Gemini models failed: "+" | ".join(errors))

def plan_story(mode,topic,count):
    direction=("Write a scientifically responsible, curiosity-driven mini documentary for a general audience. Explain mechanisms accurately, avoid fabricated facts and sensationalism, and end with a memorable takeaway."
      if mode=="science" else
      "Write an original animated short with memorable characters, a clear goal, obstacles, emotional growth and a satisfying ending. Maintain exact character appearance, clothing, colors and setting continuity. Do not imitate existing franchises or named artists.")
    subject=topic.strip() or "Invent a fresh and compelling subject yourself."
    prompt=f"""Act as a professional screenwriter, documentary writer and storyboard artist.
MODE: {mode}
{direction}
SUBJECT: {subject}
Create exactly {count} scenes for a narrated 16:9 video. Return JSON only:
{{"title":"title","description":"2 sentence summary","visual_style":"consistent visual treatment",
"continuity_bible":"recurring character or visual continuity details",
"scenes":[{{"scene_number":1,"heading":"short heading","narration":"2-4 natural spoken sentences",
"visual_description":"concrete visible action/composition","image_prompt":"standalone detailed image prompt with camera, lighting, style, 16:9, no text/logo/watermark"}}]}}
Rules: exactly {count} scenes numbered 1..{count}; all fields non-empty; coherent beginning/middle/end; each prompt independently usable and includes relevant continuity details. Science must be factual; animation must be original."""
    data=gemini(prompt); scenes=data.get("scenes")
    if not isinstance(scenes,list) or len(scenes)!=count: raise ValueError(f"Expected {count} scenes")
    for i,s in enumerate(scenes,1):
        if not isinstance(s,dict) or s.get("scene_number")!=i: raise ValueError(f"Scene {i} out of order")
        for k in ("heading","narration","visual_description","image_prompt"):
            if not isinstance(s.get(k),str) or not s[k].strip(): raise ValueError(f"Scene {i}: missing {k}")
    for k in ("title","description","visual_style","continuity_bible"):
        if not isinstance(data.get(k),str) or not data[k].strip(): raise ValueError(f"Missing {k}")
    return data

def valid_png(raw):
    if not raw: raise ValueError("Empty image response")
    with Image.open(io.BytesIO(raw)) as im: im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im=im.convert("RGB"); b=io.BytesIO(); im.save(b,"PNG",optimize=True); return b.getvalue()

def ovh(prompt):
    r=requests.post("https://stable-diffusion-xl.endpoints.kepler.ai.cloud.ovh.net/api/text2image",
      headers={"accept":"application/octet-stream","Content-Type":"application/json"},
      json={"prompt":prompt,"negative_prompt":"text, watermark, logo, blurry, low quality"},timeout=TIMEOUT)
    r.raise_for_status()
    if "application/json" in r.headers.get("Content-Type",""):
        encoded=(r.json().get("data") or [{}])[0].get("b64_json")
        if not encoded: raise ValueError("OVH returned no image data")
        return valid_png(base64.b64decode(encoded))
    return valid_png(r.content)

def pollinations(prompt):
    url="https://image.pollinations.ai/prompt/"+requests.utils.quote(prompt,safe="")
    r=requests.get(url,params={"width":1280,"height":720,"nologo":"true"},headers={"Accept":"image/*"},timeout=TIMEOUT)
    r.raise_for_status(); return valid_png(r.content)

def generate_all(scenes,folder):
    folder.mkdir(parents=True,exist_ok=True); failures=[]
    for s in scenes:
        n=s["scene_number"]; target=folder/f"scene-{n:02d}.png"; errors=[]
        for name,fn in (("OVHcloud anonymous",ovh),("Pollinations anonymous",pollinations)):
            try:
                target.write_bytes(valid_png(fn(s["image_prompt"])))
                print(f"Image {n}/{len(scenes)} generated with {name}",flush=True); break
            except Exception as e:
                errors.append(f"{name}: {e}"); print(f"Scene {n}: {name} failed: {e}",file=sys.stderr,flush=True)
        else: failures.append({"scene":n,"errors":errors})
    if failures: raise RuntimeError("Missing scene images; video render cancelled: "+json.dumps(failures))

async def speak(text,path,voice):
    last=None
    for attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            await asyncio.wait_for(edge_tts.Communicate(text=text,voice=voice,rate="+0%").save(str(path)),timeout=240)
            if path.exists() and path.stat().st_size>1000: return
            raise RuntimeError("Empty narration audio")
        except Exception as e:
            last=e; path.unlink(missing_ok=True)
            if attempt<4: await asyncio.sleep(min(30,2**(attempt+1)))
    raise RuntimeError(f"Edge TTS failed: {last}")

def command(args):
    subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)

def render(scenes,package,voice):
    aud=package/"audio"; seg=package/"segments"; aud.mkdir(); seg.mkdir(); parts=[]
    for s in scenes:
        n=s["scene_number"]; audio=aud/f"scene-{n:02d}.mp3"; video=seg/f"segment-{n:02d}.mp4"
        asyncio.run(speak(s["narration"],audio,voice))
        command(["ffmpeg","-y","-loop","1","-i",str(package/"images"/f"scene-{n:02d}.png"),"-i",str(audio),
          "-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p",
          "-r","25","-c:v","libx264","-preset","veryfast","-tune","stillimage","-c:a","aac","-b:a","128k",
          "-shortest","-movflags","+faststart",str(video)])
        parts.append(video); print(f"Scene {n}/{len(scenes)} narrated and rendered",flush=True)
    concat=package/"concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts),encoding="utf-8")
    final=package/"final-video.mp4"
    command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart",str(final)])
    if not final.exists() or final.stat().st_size<100000: raise RuntimeError("Final MP4 missing or too small")
    return final

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("science","animated"),required=True)
    p.add_argument("--topic",default="")
    p.add_argument("--scenes",type=int,default=8)
    p.add_argument("--voice",default="en-US-AndrewMultilingualNeural")
    a=p.parse_args()
    if not 4<=a.scenes<=16: p.error("Scene count must be 4–16")
    OUT.mkdir(exist_ok=True)
    package=OUT/(time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-"+a.mode); package.mkdir()
    data=plan_story(a.mode,a.topic,a.scenes); data.update({"mode":a.mode,"scene_count":a.scenes,"voice":a.voice})
    (package/"story.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    script="# "+data["title"]+"\n\n"+data["description"]+"\n\n"
    script+="\n\n".join(f"## Scene {s['scene_number']}: {s['heading']}\n\n{s['narration']}\n\n**Visual:** {s['visual_description']}" for s in data["scenes"])
    (package/"script.md").write_text(script,encoding="utf-8")
    (package/"images").mkdir()
    generate_all(data["scenes"],package/"images")
    final=render(data["scenes"],package,a.voice)
    print("FINAL_VIDEO="+str(final)); print("STORY_PACKAGE="+str(package))
if __name__=="__main__": main()

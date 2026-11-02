#!/usr/bin/env python3
"""Gemini-planned science documentaries and animated stories rendered from generated stills."""
import argparse, asyncio, base64, io, json, os, re, subprocess, sys, time
from pathlib import Path
import edge_tts, requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"ai-story-video-output"
KEY=os.getenv("GEMINI_API_KEY","").strip()
MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash").strip()
FALLBACK=[x.strip() for x in os.getenv("GEMINI_FALLBACK_MODELS","gemini-3.5-flash-lite").split(",") if x.strip()]
TIMEOUT=(20,180)
_OVH_LAST_CALL=0.0

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

def plan_story(topic,count):
    topics_file=ROOT/"topics.txt"
    if not topics_file.is_file():
        raise FileNotFoundError("Required topic inspiration file is missing: topics.txt")
    topic_examples=[line.strip() for line in topics_file.read_text(encoding="utf-8-sig").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    if not topic_examples:
        raise ValueError("topics.txt is empty; add topic examples before running.")
    topic_library="\n".join("- "+item for item in topic_examples)
    direction="You are the creative director and writer. Decide whether the best video is a scientifically responsible science documentary or an original animated story. Choose the format yourself based on the newly invented topic and audience appeal. For science, explain mechanisms accurately and avoid fabricated facts. For animation, create memorable original characters, a clear goal, obstacles, emotional growth and a satisfying ending. Maintain character appearance and setting continuity. All visuals must be polished cinematic 3D CGI with convincing depth, detailed materials and cinematic lighting. Do not imitate any specific studio, film, franchise, copyrighted character or named artist."
    user_hint=topic.strip() or "No additional user hint."
    prompt=f"""Act as a professional topic researcher, screenwriter, documentary writer and storyboard artist.
{direction}
TOPIC INSPIRATION LIBRARY (read every example):
{topic_library}

IMPORTANT TOPIC NOVELTY RULES:
- Treat topics.txt as a library of subject areas, curiosity styles, question patterns and broad themes—not as a list to copy.
- Invent ONE genuinely new topic inspired by the interests and style of the library.
- Do NOT select, repeat, quote, lightly reword, paraphrase, or make a near-duplicate of any listed topic.
- Explore a different specific phenomenon, question, mechanism, surprising connection or thought experiment within a related broad subject area.
- The generated title and central question must be clearly distinct from every entry above.
- If a user hint is supplied, use it only as an additional interest signal; still create a fresh topic and do not copy the hint verbatim.
USER INTEREST HINT: {user_hint}
Choose science documentary or original animated story to suit your new topic.
Create exactly {count} scenes for a narrated 16:9 video. Return JSON only:
{{"mode":"science or animated","title":"a newly invented topic/title, not copied from topics.txt","description":"2 sentence summary","visual_style":"consistent visual treatment",
"continuity_bible":"recurring character or visual continuity details",
"scenes":[{{"scene_number":1,"heading":"short heading","narration":"2-4 natural spoken sentences",
"visual_description":"concrete visible action/composition","image_prompt":"standalone detailed prompt for a polished 3D CGI render; specify camera, composition, lighting, materials, depth and visual style; 16:9; no text, logo or watermark"}}]}}
Rules: exactly {count} scenes numbered 1..{count}; all fields non-empty; coherent beginning/middle/end; each prompt independently usable and includes relevant continuity details. Every scene must be a polished 3D CGI image, not a 2D illustration. Science must be factual; animation must be original and must not copy any existing studio, franchise, film or character design. The title and story must be based on your newly invented topic, not an existing topics.txt entry."""
    data=gemini(prompt); scenes=data.get("scenes")
    if data.get("mode") not in ("science","animated"): raise ValueError("Gemini must classify mode as science or animated")
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
    global _OVH_LAST_CALL
    wait=max(0.0,35.0-(time.monotonic()-_OVH_LAST_CALL))
    if wait: time.sleep(wait)
    _OVH_LAST_CALL=time.monotonic()
    r=requests.post("https://stable-diffusion-xl.endpoints.kepler.ai.cloud.ovh.net/api/text2image",
      headers={"accept":"application/octet-stream","Content-Type":"application/json"},
      json={"prompt":prompt,"negative_prompt":"text, watermark, logo, blurry, low quality"},timeout=TIMEOUT)
    r.raise_for_status()
    if "application/json" in r.headers.get("Content-Type",""):
        encoded=(r.json().get("data") or [{}])[0].get("b64_json")
        if not encoded: raise ValueError("OVH returned no image data")
        return valid_png(base64.b64decode(encoded))
    return valid_png(r.content)

def ai_horde(prompt):
    base="https://aihorde.net/api/v2"
    headers={"apikey":"0000000000","Client-Agent":"stickman-lab:1.0:https://github.com/manojkumar166-png/stickman-lab"}
    payload={"prompt":prompt+"###text, watermark, logo, blurry, low quality",
      "params":{"width":1024,"height":576,"steps":20,"n":1},
      "nsfw":False,"censor_nsfw":True,"trusted_workers":False}
    r=requests.post(base+"/generate/async",headers=headers,json=payload,timeout=60)
    r.raise_for_status(); job=r.json().get("id")
    if not job: raise RuntimeError("AI Horde returned no job ID")
    deadline=time.monotonic()+600
    while time.monotonic()<deadline:
        time.sleep(5)
        check=requests.get(base+f"/generate/check/{job}",headers=headers,timeout=45)
        check.raise_for_status(); state=check.json()
        if state.get("faulted"): raise RuntimeError("AI Horde generation faulted")
        if state.get("done"): break
    else: raise TimeoutError("AI Horde queue timed out after 10 minutes")
    result=requests.get(base+f"/generate/status/{job}",headers=headers,timeout=60)
    result.raise_for_status(); generations=result.json().get("generations") or []
    if not generations: raise RuntimeError("AI Horde completed without an image")
    img=generations[0].get("img")
    if not img: raise RuntimeError("AI Horde response contained no image")
    if img.startswith("data:") and "," in img:
        return valid_png(base64.b64decode(img.split(",",1)[1]))
    if img.startswith("http://") or img.startswith("https://"):
        download=requests.get(img,timeout=TIMEOUT); download.raise_for_status(); return valid_png(download.content)
    try: return valid_png(base64.b64decode(img,validate=True))
    except Exception as e: raise RuntimeError(f"Unrecognized AI Horde image payload: {e}")

def vexa(prompt):
    errors=[]
    for model in ("hd","flux"):
        try:
            r=requests.post("https://vexa-ai.pages.dev/image",
                json={"prompt":prompt[:1000],"model":model,"preference":"quality"},timeout=TIMEOUT)
            r.raise_for_status(); data=r.json()
            if not data.get("success") or not data.get("proxy_url"):
                raise RuntimeError(data.get("error") or "Vexa returned no proxy URL")
            image=requests.get(data["proxy_url"],timeout=TIMEOUT); image.raise_for_status()
            return valid_png(image.content)
        except Exception as e: errors.append(f"{model}: {e}")
    raise RuntimeError("Vexa routes failed: "+" | ".join(errors))

def pollinations(prompt):
    url="https://image.pollinations.ai/prompt/"+requests.utils.quote(prompt,safe="")
    r=requests.get(url,params={"width":1280,"height":720,"nologo":"true"},headers={"Accept":"image/*"},timeout=TIMEOUT)
    r.raise_for_status(); return valid_png(r.content)

def generate_all(scenes,folder):
    folder.mkdir(parents=True,exist_ok=True); failures=[]
    providers=(("OVHcloud anonymous",ovh,2),("AI Horde anonymous",ai_horde,1),
               ("Vexa/DeepAI+Flux anonymous",vexa,1),("Pollinations direct",pollinations,1))
    for s in scenes:
        n=s["scene_number"]; target=folder/f"scene-{n:02d}.png"; errors=[]; completed=False
        for name,fn,retries in providers:
            for attempt in range(retries):
                print(f"Scene {n}/{len(scenes)}: trying {name} (attempt {attempt+1}/{retries})",flush=True)
                try:
                    target.write_bytes(valid_png(fn(s["image_prompt"])))
                    print(f"Image {n}/{len(scenes)} generated with {name}",flush=True)
                    completed=True; break
                except Exception as e:
                    errors.append(f"{name} attempt {attempt+1}: {e}")
                    print(f"Scene {n}: {name} failed: {e}",file=sys.stderr,flush=True)
                    if attempt+1<retries: time.sleep(min(90,30*(attempt+1)))
            if completed: break
        if not completed: failures.append({"scene":n,"errors":errors})
    if failures: raise RuntimeError("Missing scene images; video render cancelled: "+json.dumps(failures))
    print(f"Validated all {len(scenes)} scene images.",flush=True)

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
        print(f"Edge TTS: scene {n}/{len(scenes)}",flush=True)
        asyncio.run(speak(s["narration"],audio,voice))
        print(f"FFmpeg: rendering scene segment {n}/{len(scenes)}",flush=True)
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
    p.add_argument("--topic",default="")
    p.add_argument("--scenes",type=int,default=8)
    p.add_argument("--voice",default="en-US-AndrewMultilingualNeural")
    a=p.parse_args()
    if not 4<=a.scenes<=48: p.error("Scene count must be 4–48")
    print("::group::RUN CONFIGURATION",flush=True)
    print(f"Format=Gemini decides | Scenes={a.scenes} | Voice={a.voice}",flush=True)
    print("Images: anonymous OVHcloud -> AI Horde -> Vexa -> Pollinations. Cloudflare is not used.",flush=True)
    print("Narration: Edge TTS | Rendering: FFmpeg | Delivery: GitHub Actions artifact",flush=True)
    print("::endgroup::",flush=True)
    OUT.mkdir(exist_ok=True)
    package=OUT/(time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-gemini"); package.mkdir()
    print("::group::STEP 1/5 - Gemini story planning",flush=True)
    data=plan_story(a.topic,a.scenes); data.update({"scene_count":a.scenes,"voice":a.voice})
    print("Gemini selected format: "+data["mode"],flush=True)
    (package/"story.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Story validated: {data['title']} | {len(data['scenes'])} scenes",flush=True)
    print("::endgroup::",flush=True)
    script="# "+data["title"]+"\n\n"+data["description"]+"\n\n"
    script+="\n\n".join(f"## Scene {s['scene_number']}: {s['heading']}\n\n{s['narration']}\n\n**Visual:** {s['visual_description']}" for s in data["scenes"])
    (package/"script.md").write_text(script,encoding="utf-8")
    (package/"images").mkdir()
    print("::group::STEP 2/5 - Generate and validate scene images",flush=True)
    print(f"Generating {len(data['scenes'])} individual images. Cloudflare is not used.",flush=True)
    generate_all(data["scenes"],package/"images")
    print(f"All {len(data['scenes'])} scene images passed validation.",flush=True)
    print("::endgroup::",flush=True)
    print("::group::STEP 3/5 - Edge TTS narration and STEP 4/5 - FFmpeg rendering",flush=True)
    final=render(data["scenes"],package,a.voice)
    print("::endgroup::",flush=True)
    print("STEP 5/5 - Package complete; artifact upload is the next GitHub Actions step.",flush=True)
    print("FINAL_VIDEO="+str(final)); print("STORY_PACKAGE="+str(package))
if __name__=="__main__": main()

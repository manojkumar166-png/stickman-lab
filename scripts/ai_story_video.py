#!/usr/bin/env python3
"""Gemini-planned science documentaries and animated stories rendered from generated stills."""
import argparse, asyncio, base64, io, json, os, re, subprocess, sys, time
from pathlib import Path
import edge_tts, requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"ai-story-video-output"
KEY=os.getenv("GEMINI_API_KEY","").strip()
# Keep planner calls on Gemini API models listed as free-tier eligible.
# Paid or unknown model IDs supplied through Actions variables are ignored.
FREE_GEMINI_MODELS=(
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
_requested_model=os.getenv("GEMINI_MODEL","gemini-3.8-flash").strip()
MODEL=_requested_model if _requested_model in FREE_GEMINI_MODELS else "gemini-3.8-flash"
_requested_fallbacks=os.getenv("GEMINI_FALLBACK_MODELS",",".join(FREE_GEMINI_MODELS[1:]))
FALLBACK=[
    model for model in (x.strip() for x in _requested_fallbacks.split(","))
    if model in FREE_GEMINI_MODELS and model != MODEL
]
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
    history_file=ROOT/"used_story_topics.json"
    used_topics=[]
    if history_file.is_file():
        history=json.loads(history_file.read_text(encoding="utf-8"))
        if isinstance(history,list):
            used_topics=[item for item in history if isinstance(item,dict)]
    used_library="\n".join(
        "- Title: "+str(item.get("title",""))+" | Core topic: "+str(item.get("topic",""))+" | Summary: "+str(item.get("description",""))
        for item in used_topics
    ) or "- No previous topics recorded."
    direction="You are the creative director and writer. Decide whether the best video is a scientifically responsible science documentary or an original animated story. Choose the format yourself based on the newly invented topic and audience appeal. For science, explain mechanisms accurately and avoid fabricated facts. For animation, create memorable original characters, a clear goal, obstacles, emotional growth and a satisfying ending. Maintain character appearance and setting continuity. All visuals must be polished cinematic 3D CGI with convincing depth, detailed materials and cinematic lighting. Do not imitate any specific studio, film, franchise, copyrighted character or named artist."
    user_hint=topic.strip() or "No additional user hint."
    prompt=f"""Act as a professional topic researcher, screenwriter, documentary writer and storyboard artist.
{direction}
TOPIC INSPIRATION LIBRARY (read every example):
{topic_library}

PREVIOUSLY USED TOPICS — DO NOT REUSE THESE CORE SUBJECTS:
{used_library}

IMPORTANT TOPIC NOVELTY RULES:
- Treat topics.txt as a library of subject areas, curiosity styles, question patterns and broad themes—not as a list to copy.
- Invent ONE genuinely new topic inspired by the interests and style of the library.
- Do NOT select, repeat, quote, lightly reword, paraphrase, or make a near-duplicate of any listed topic.
- Explore a different specific phenomenon, question, mechanism, surprising connection or thought experiment within a related broad subject area.
- The generated title and central question must be clearly distinct from every topics.txt entry.
- Never reuse a previously used core topic, phenomenon or central question, even with a different title, wording, character, setting or format.
- A broad subject area may be reused if the specific underlying topic is genuinely different. For example, another space topic is acceptable, but retelling the same black-hole concept with a new title is not.
- If a user hint is supplied, use it only as an additional interest signal; still create a fresh topic and do not copy the hint verbatim.
USER INTEREST HINT: {user_hint}
Choose science documentary or original animated story to suit your new topic.
Create exactly {count} scenes for a narrated 16:9 video. Return JSON only:
{{"mode":"science or animated","title":"a newly invented title","topic":"one-sentence statement of the specific core phenomenon or subject; precise enough to detect reuse","description":"2 sentence summary","visual_style":"consistent visual treatment",
"continuity_bible":"recurring character or visual continuity details",
"scenes":[{{"scene_number":1,"heading":"short heading","narration":"2-4 natural spoken sentences",
"visual_description":"concrete visible action/composition","image_prompt":"standalone detailed prompt for a polished 3D CGI render; specify camera, composition, lighting, materials, depth and visual style; 16:9; no text, logo or watermark"}}]}}
Rules: exactly {count} scenes numbered 1..{count}; all fields non-empty; coherent beginning/middle/end; each prompt independently usable and includes relevant continuity details. Every scene must be a polished 3D CGI image, not a 2D illustration. For every scene, ALWAYS include all four non-empty fields: heading, narration, visual_description, and image_prompt. visual_description must be a short plain-language description and must not be omitted. Science must be factual; animation must be original and must not copy any existing studio, franchise, film or character design. The title and story must be based on a newly invented topic, not an existing topics.txt entry or a previously used core topic."""
    data=gemini(prompt); scenes=data.get("scenes")
    if data.get("mode") not in ("science","animated"): raise ValueError("Gemini must classify mode as science or animated")
    if not isinstance(scenes,list) or len(scenes)!=count: raise ValueError(f"Expected {count} scenes")
    for i,s in enumerate(scenes,1):
        if not isinstance(s,dict) or s.get("scene_number")!=i: raise ValueError(f"Scene {i} out of order")
        # Gemini occasionally omits the redundant visual_description field even
        # when it supplies a complete image_prompt. Recover it deterministically
        # rather than failing the entire run for missing descriptive metadata.
        for k in ("heading","narration","image_prompt"):
            if not isinstance(s.get(k),str) or not s[k].strip():
                raise ValueError(f"Scene {i}: missing required {k}; planner output cannot be safely recovered")
        if not isinstance(s.get("visual_description"),str) or not s["visual_description"].strip():
            s["visual_description"] = s["image_prompt"].strip()
            print(f"Scene {i}: visual_description was omitted; recovered it from image_prompt.",flush=True)
    for k in ("title","topic","description","visual_style","continuity_bible"):
        if not isinstance(data.get(k),str) or not data[k].strip(): raise ValueError(f"Missing {k}")
    normalize=lambda value: re.sub(r"[^a-z0-9]+"," ",value.casefold()).strip()
    if normalize(data["title"]) in {normalize(item) for item in topic_examples}:
        raise ValueError("Gemini copied a title from topics.txt instead of inventing a new topic.")
    used_core={normalize(item.get("topic","")) for item in used_topics if item.get("topic")}
    if normalize(data["topic"]) in used_core:
        raise ValueError("Gemini selected a previously used core topic. Choose a different subject.")
    return data

def valid_png(raw):
    if not raw: raise ValueError("Empty image response")
    with Image.open(io.BytesIO(raw)) as im: im.verify()
    with Image.open(io.BytesIO(raw)) as im:
        im=im.convert("RGB"); b=io.BytesIO(); im.save(b,"PNG",optimize=True); return b.getvalue()

CF_ACCOUNT_ID=os.getenv("CF_ACCOUNT_ID","").strip()
CF_API_TOKEN=os.getenv("CF_API_TOKEN","").strip()
CF_URL=f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
class CloudflareRateLimited(RuntimeError): pass

def cloudflare_image(prompt):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN: raise RuntimeError("Configure CF_ACCOUNT_ID and CF_API_TOKEN secrets.")
    for attempt in range(1,4):
        r=requests.post(CF_URL,headers={"Authorization":f"Bearer {CF_API_TOKEN}"},json={"prompt":prompt,"width":1024,"height":576},timeout=TIMEOUT)
        if r.status_code==429:
            try: wait=max(60,min(1800,int(float(r.headers.get("Retry-After","300")))))
            except ValueError: wait=300*attempt
            if attempt==3: raise CloudflareRateLimited("Cloudflare rate limit persisted after three attempts.")
            print(f"Cloudflare 429; waiting {wait}s before retry {attempt+1}/3.",flush=True); time.sleep(wait); continue
        if r.status_code>=500 and attempt<3: time.sleep(30*attempt); continue
        r.raise_for_status(); payload=r.json(); result=payload.get("result") or {}
        encoded=result.get("image") or result.get("b64_json")
        if not encoded: raise RuntimeError(f"Cloudflare returned no image: {str(payload)[:400]}")
        return valid_png(base64.b64decode(encoded))
    raise CloudflareRateLimited("Cloudflare unavailable.")

def generate_all(scenes,folder):
    folder.mkdir(parents=True,exist_ok=True)
    for s in scenes:
        n=s["scene_number"]; target=folder/f"scene-{n:02d}.png"
        if target.is_file() and target.stat().st_size>0:
            try: valid_png(target.read_bytes()); print(f"Scene {n} already saved; skipping.",flush=True); continue
            except Exception: target.unlink(missing_ok=True)
        print(f"Scene {n}/{len(scenes)}: Cloudflare only.",flush=True)
        target.write_bytes(valid_png(cloudflare_image(generation_prompt(s))))
        print(f"Scene {n} saved.",flush=True); time.sleep(2)
    print(f"Validated all {len(scenes)} images.",flush=True)

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
    print("Images: free anonymous providers; cinematic prompt enhancement and center-crop-safe framing; OVHcloud first.",flush=True)
    print("Narration: Edge TTS | Rendering: FFmpeg | Delivery: GitHub Actions artifact",flush=True)
    print("::endgroup::",flush=True)
    OUT.mkdir(exist_ok=True)
    package=None
    data=None
    for candidate in sorted((x for x in OUT.iterdir() if x.is_dir()),key=lambda x:x.name,reverse=True):
        sf=candidate/"story.json"
        if sf.is_file() and not (candidate/"final-video.mp4").is_file():
            try:
                saved=json.loads(sf.read_text(encoding="utf-8"))
                if len(saved.get("scenes",[]))==a.scenes:
                    package=candidate; data=saved
                    print(f"Resuming {candidate.name}",flush=True); break
            except Exception: pass
    if package is None:
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
    (package/"images").mkdir(exist_ok=True)
    print("::group::STEP 2/5 - Generate and validate scene images",flush=True)
    print(f"Generating {len(data['scenes'])} individual images. Cloudflare only.",flush=True)
    generate_all(data["scenes"],package/"images")
    print(f"All {len(data['scenes'])} scene images passed validation.",flush=True)
    print("::endgroup::",flush=True)
    print("::group::STEP 3/5 - Edge TTS narration and STEP 4/5 - FFmpeg rendering",flush=True)
    final=render(data["scenes"],package,a.voice)
    print("::endgroup::",flush=True)
    history_file=ROOT/"used_story_topics.json"
    history=json.loads(history_file.read_text(encoding="utf-8")) if history_file.is_file() else []
    history.append({"title":data["title"],"topic":data["topic"],"description":data["description"]})
    history_file.write_text(json.dumps(history,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Recorded this completed topic in used_story_topics.json for future runs.",flush=True)
    print("STEP 5/5 - Package complete; artifact upload is the next GitHub Actions step.",flush=True)
    print("FINAL_VIDEO="+str(final)); print("STORY_PACKAGE="+str(package))
if __name__=="__main__": main()

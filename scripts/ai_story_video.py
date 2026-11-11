#!/usr/bin/env python3
"""Gemini-planned science documentaries and animated stories rendered from generated stills."""
import argparse, asyncio, base64, io, json, os, re, subprocess, sys, time
from pathlib import Path
import edge_tts, requests
from gtts import gTTS
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"ai-story-video-output"
KEY=os.getenv("GEMINI_API_KEY","").strip()
GROQ_KEY=os.getenv("GROQ_API_KEY","").strip()
GROQ_MODEL=os.getenv("GROQ_MODEL","openai/gpt-oss-120b").strip()
KILO_MODEL=os.getenv("KILO_MODEL","kilo-auto/free").strip()
KILO_FALLBACK_MODELS=[x.strip() for x in os.getenv("KILO_FALLBACK_MODELS","nvidia/nemotron-3.5-super-vl:free,dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free").split(",") if x.strip()]
OVH_MODEL=os.getenv("OVH_MODEL","Qwen3.5-397B-A17B").strip()
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
    if start<0: raise ValueError("LLM returned no JSON object")
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
    raise ValueError("LLM returned incomplete JSON")

def gemini(prompt):
    errors=[]
    if KEY:
        for model in dict.fromkeys([MODEL]+FALLBACK):
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(1,4):
                try:
                    r=requests.post(
                        url,
                        params={"key":KEY},
                        json={"contents":[{"parts":[{"text":prompt}]}],
                              "generationConfig":{"responseMimeType":"application/json","temperature":0.8}},
                        timeout=(20,180),
                    )
                    if r.status_code in (400,403,404):
                        error=f"Gemini {model} permanent HTTP {r.status_code}: {r.text[:900]}"
                        errors.append(error)
                        print(error,flush=True)
                        break
                    if r.status_code in (408,429,500,502,503,504):
                        raise RuntimeError(f"Gemini {model} HTTP {r.status_code}: {r.text[:900]}")
                    r.raise_for_status()
                    candidates=r.json().get("candidates") or []
                    parts=candidates[0].get("content",{}).get("parts",[]) if candidates else []
                    result=parse_json("".join(p.get("text","") for p in parts if isinstance(p,dict)))
                    print(f"Gemini planner active: {model}",flush=True)
                    return result
                except Exception as exc:
                    errors.append(f"{model} try {attempt}/3: {type(exc).__name__}: {exc}")
                    if attempt<3:
                        delay=min(30,2**(attempt+1))
                        print(f"Gemini {model} transient failure; retrying in {delay}s ({attempt}/3).",flush=True)
                        time.sleep(delay)
    else:
        errors.append("GEMINI_API_KEY is not configured; skipped Gemini.")
        print("Gemini skipped: GEMINI_API_KEY is not configured.",flush=True)

    # Groq is the first open-weight backup. It is optional; the no-key Kilo
    # free-model gateway below remains available when this secret is absent.
    groq_errors=[]
    if GROQ_KEY:
        groq_url="https://api.groq.com/openai/v1/chat/completions"
        for attempt in range(1,4):
            try:
                response=requests.post(groq_url,
                    headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                    json={"model":GROQ_MODEL,"messages":[
                        {"role":"system","content":"Return only a valid JSON object matching the user's requested schema. Follow all instructions precisely."},
                        {"role":"user","content":prompt}],
                        "response_format":{"type":"json_object"},"temperature":0.8,"max_completion_tokens":32768},
                    timeout=TIMEOUT)
                if response.status_code in (408,429,500,502,503,504):
                    raise RuntimeError(f"Groq HTTP {response.status_code}: {response.text[:500]}")
                response.raise_for_status()
                choices=response.json().get("choices") or []
                content=choices[0].get("message",{}).get("content","") if choices else ""
                result=parse_json(content)
                print(f"Open-weight planner backup active: Groq {GROQ_MODEL}",flush=True)
                return result
            except Exception as exc:
                groq_errors.append(f"try {attempt}: {type(exc).__name__}: {exc}")
                if attempt<3:
                    delay=min(20,2**attempt)
                    print(f"Groq backup attempt {attempt}/3 failed: {exc}. Retrying in {delay}s.",flush=True)
                    time.sleep(delay)
    else:
        print("Groq skipped: GROQ_API_KEY is not configured.",flush=True)

    # Kilo's free auto-router is OpenAI-compatible and supports anonymous
    # requests for free models, so no KILO_API_KEY is required here.
    kilo_url="https://ai-gateway.kilo.ai/api/v1/chat/completions"
    kilo_errors=[]
    kilo_models=list(dict.fromkeys([KILO_MODEL]+KILO_FALLBACK_MODELS))
    for kilo_model in kilo_models:
        messages=[
            {"role":"system","content":"Return only one valid JSON object matching the user's requested schema. Do not use Markdown fences or add commentary."},
            {"role":"user","content":prompt},
        ]
        request_bodies=[
            {"model":kilo_model,"messages":messages,"max_tokens":16384},
            {"model":kilo_model,"messages":messages},
        ]
        for attempt in range(1,3):
            try:
                response=None
                for variant_index,body in enumerate(request_bodies):
                    response=requests.post(
                        kilo_url,
                        headers={"Content-Type":"application/json"},
                        json=body,
                        timeout=(20,240),
                    )
                    if response.status_code==400 and variant_index+1<len(request_bodies):
                        message=f"Kilo model {kilo_model} rejected optional token limits; retrying minimal request."
                        print(message,flush=True)
                        continue
                    if response.status_code in (408,425,429,500,502,503,504):
                        raise RuntimeError(f"Kilo HTTP {response.status_code}: {response.text[:1200]}")
                    if not response.ok:
                        error=f"Kilo model {kilo_model} HTTP {response.status_code}: {response.text[:1400]}"
                        kilo_errors.append(error)
                        print(error,flush=True)
                        if 400<=response.status_code<500:
                            break
                        raise RuntimeError(error)
                    break
                if response is None or not response.ok:
                    break
                choices=response.json().get("choices") or []
                message=choices[0].get("message",{}) if choices else {}
                content=message.get("content","")
                if isinstance(content,list):
                    content="".join(part.get("text","") for part in content if isinstance(part,dict))
                result=parse_json(content)
                print(f"Free planner backup active: Kilo {kilo_model} (anonymous access)",flush=True)
                return result
            except Exception as exc:
                kilo_errors.append(f"{kilo_model} try {attempt}: {type(exc).__name__}: {exc}")
                if attempt<2:
                    delay=attempt*7
                    print(f"Kilo model {kilo_model} attempt {attempt}/2 failed: {exc}. Retrying in {delay}s.",flush=True)
                    time.sleep(delay)

    # Last-resort anonymous endpoint from OVHcloud. Its public tier is
    # limited to two requests per minute per IP and model, so retry slowly.
    global _OVH_LAST_CALL
    ovh_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
    ovh_errors=[]
    for attempt in range(1,3):
        try:
            if _OVH_LAST_CALL:
                wait=max(0,31-(time.monotonic()-_OVH_LAST_CALL))
                if wait:
                    print(f"Respecting OVHcloud anonymous limit; waiting {wait:.1f}s.",flush=True)
                    time.sleep(wait)
            _OVH_LAST_CALL=time.monotonic()
            response=requests.post(ovh_url,
                headers={"Content-Type":"application/json"},
                json={"model":OVH_MODEL,"messages":[
                    {"role":"system","content":"Return only one valid JSON object matching the user's requested schema. Do not use Markdown fences or add commentary."},
                    {"role":"user","content":prompt}],
                    "temperature":0.8,"max_tokens":32768},
                timeout=(20,240))
            if response.status_code in (408,425,429,500,502,503,504):
                raise RuntimeError(f"OVHcloud HTTP {response.status_code}: {response.text[:900]}")
            if not response.ok:
                raise RuntimeError(f"OVHcloud HTTP {response.status_code}: {response.text[:1200]}")
            choices=response.json().get("choices") or []
            message=choices[0].get("message",{}) if choices else {}
            content=message.get("content","")
            if isinstance(content,list):
                content="".join(part.get("text","") for part in content if isinstance(part,dict))
            result=parse_json(content)
            print(f"Free anonymous planner backup active: OVHcloud {OVH_MODEL}",flush=True)
            return result
        except Exception as exc:
            ovh_errors.append(f"try {attempt}: {type(exc).__name__}: {exc}")
            if attempt<2:
                print(f"OVHcloud anonymous backup attempt {attempt}/2 failed: {exc}. Retrying after the 2 RPM window.",flush=True)

    raise RuntimeError(
        "All planner providers failed. Gemini: "+" | ".join(errors)
        +" | Groq: "+(" | ".join(groq_errors) if groq_errors else "not configured")
        +" | Kilo: "+" | ".join(kilo_errors)
        +" | OVHcloud: "+" | ".join(ovh_errors)
    )

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

def ovh(prompt):
    global _OVH_LAST_CALL
    wait=max(0.0,31.0-(time.monotonic()-_OVH_LAST_CALL))
    if wait: time.sleep(wait)
    _OVH_LAST_CALL=time.monotonic()
    r=requests.post("https://stable-diffusion-xl.endpoints.kepler.ai.cloud.ovh.net/api/text2image",
      headers={"accept":"application/octet-stream","Content-Type":"application/json"},
      json={"prompt":prompt,"negative_prompt":"text, letters, typography, watermark, logo, signature, border, collage, split screen, duplicate subjects, extra limbs, malformed hands, deformed face, distorted anatomy, blurry, pixelated, low detail, flat lighting, oversaturated, noisy, jpeg artifacts"},timeout=TIMEOUT)
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

def generation_prompt(scene):
    base=scene["image_prompt"].strip()
    quality=("Premium cinematic 3D CGI still for a polished science documentary or original animated film; "
      "physically based materials, fine surface detail, believable scale, clear subject separation, "
      "natural cinematic color grading, realistic global illumination, crisp focal subject, controlled highlights "
      "and shadows, coherent environment. Compose as a wide 16:9 movie frame even if the generator returns a square "
      "image; keep faces, key objects and the main action within the central horizontal band, away from top/bottom "
      "edges. One unified scene, intentional camera framing, no text.")
    return base+"\n\n"+quality


def generate_all(scenes,folder):
    folder.mkdir(parents=True,exist_ok=True)
    failures=[]
    providers=(("OVHcloud anonymous",ovh,2),("AI Horde anonymous",ai_horde,1),
               ("Vexa/DeepAI+Flux anonymous",vexa,1),("Pollinations direct",pollinations,1))
    for s in scenes:
        n=s["scene_number"]
        target=folder/f"scene-{n:02d}.png"
        if target.is_file():
            try:
                target.write_bytes(valid_png(target.read_bytes()))
                print(f"Scene {n}/{len(scenes)}: valid checkpoint image found; skipping generation.",flush=True)
                continue
            except Exception as exc:
                print(f"Scene {n}: removing invalid checkpoint image: {exc}",flush=True)
                target.unlink(missing_ok=True)
        errors=[]
        completed=False
        prompt=generation_prompt(s)
        for name,fn,retries in providers:
            for attempt in range(retries):
                print(f"Scene {n}/{len(scenes)}: trying {name} (attempt {attempt+1}/{retries})",flush=True)
                try:
                    image=valid_png(fn(prompt))
                    temporary=target.with_name(target.name+".tmp")
                    temporary.write_bytes(image)
                    temporary.replace(target)
                    print(f"Image {n}/{len(scenes)} generated with {name}",flush=True)
                    completed=True
                    break
                except Exception as e:
                    errors.append(f"{name} attempt {attempt+1}: {type(e).__name__}: {e}")
                    print(f"Scene {n}: {name} failed: {e}",file=sys.stderr,flush=True)
                    if attempt+1<retries:
                        time.sleep(min(90,30*(attempt+1)))
            if completed:
                break
        if not completed:
            failures.append({"scene":n,"errors":errors})
    if failures:
        raise RuntimeError("Missing scene images; completed images are checkpointed for the next run: "+json.dumps(failures))
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
    print(f"Edge TTS failed after 5 attempts ({last}); switching to Google TTS fallback.",file=sys.stderr,flush=True)
    try:
        path.unlink(missing_ok=True)
        gTTS(text=text, lang="en").save(str(path))
        if not path.is_file() or path.stat().st_size <= 1000:
            raise RuntimeError("Google TTS returned an empty audio file")
        print(f"Google TTS fallback completed: {path}",flush=True)
    except Exception as fallback_error:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Edge TTS failed after 5 attempts ({last}); Google TTS fallback also failed: {fallback_error}") from fallback_error

def command(args):
    """Retry transient FFmpeg failures, then use MPEG-4 if H.264 encoding fails."""
    last_error = None
    for attempt in range(1, 4):
        try:
            subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=900)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            print(f"FFmpeg attempt {attempt}/3 failed: {exc}",file=sys.stderr,flush=True)
            if attempt < 3:
                time.sleep(attempt * 5)
    if "-c:v" in args and "libx264" in args:
        fallback, skip = [], False
        for item in args:
            if skip:
                skip = False
                continue
            if item in ("-preset", "-crf", "-tune"):
                skip = True
            elif item == "libx264":
                fallback.extend(["mpeg4", "-q:v", "5"])
            else:
                fallback.append(item)
        print("FFmpeg H.264 failed after 3 attempts; trying MPEG-4 encoder fallback.",flush=True)
        subprocess.run(fallback,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=900)
        return
    raise RuntimeError(f"FFmpeg failed after 3 attempts: {last_error}") from last_error

def media_has_stream(path,selector,minimum_bytes=1024):
    path=Path(path)
    if not path.is_file() or path.stat().st_size<minimum_bytes:
        return False
    try:
        probe=subprocess.run(
            ["ffprobe","-v","error","-select_streams",selector,
             "-show_entries","stream=codec_type","-of","csv=p=0",str(path)],
            capture_output=True,text=True,timeout=30
        )
        return probe.returncode==0 and bool(probe.stdout.strip())
    except (OSError,subprocess.SubprocessError):
        return False

def render(scenes,package,voice):
    aud=package/"audio"
    seg=package/"segments"
    aud.mkdir(parents=True,exist_ok=True)
    seg.mkdir(parents=True,exist_ok=True)
    parts=[]
    for s in scenes:
        n=s["scene_number"]
        audio=aud/f"scene-{n:02d}.mp3"
        video=seg/f"segment-{n:02d}.mp4"
        if not media_has_stream(audio,"a:0",1000):
            audio.unlink(missing_ok=True)
            print(f"Edge TTS: scene {n}/{len(scenes)}",flush=True)
            asyncio.run(speak(s["narration"],audio,voice))
            if not media_has_stream(audio,"a:0",1000):
                raise RuntimeError(f"Scene {n}: Edge TTS audio failed media validation")
        else:
            print(f"Edge TTS: reusing saved audio for scene {n}/{len(scenes)}",flush=True)
        if not (media_has_stream(video,"v:0",100000) and media_has_stream(video,"a:0",100000)):
            video.unlink(missing_ok=True)
            print(f"FFmpeg: rendering scene segment {n}/{len(scenes)}",flush=True)
            command(["ffmpeg","-y","-loop","1","-i",str(package/"images"/f"scene-{n:02d}.png"),"-i",str(audio),
              "-vf","scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p",
              "-r","25","-c:v","libx264","-preset","veryfast","-tune","stillimage","-c:a","aac","-b:a","128k",
              "-shortest","-movflags","+faststart",str(video)])
            if not (media_has_stream(video,"v:0",100000) and media_has_stream(video,"a:0",100000)):
                raise RuntimeError(f"Scene {n}: FFmpeg did not produce a valid audio/video segment")
        else:
            print(f"FFmpeg: reusing saved video segment for scene {n}/{len(scenes)}",flush=True)
        parts.append(video)
    concat=package/"concat.txt"
    concat.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),encoding="utf-8")
    final=package/"final-video.mp4"
    if not (media_has_stream(final,"v:0",100000) and media_has_stream(final,"a:0",100000)):
        final.unlink(missing_ok=True)
        command(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart",str(final)])
    if not (media_has_stream(final,"v:0",100000) and media_has_stream(final,"a:0",100000)):
        raise RuntimeError("Final MP4 is missing, incomplete, or has no valid audio/video streams")
    return final
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--topic",default="")
    p.add_argument("--scenes",type=int,default=8)
    p.add_argument("--voice",default="en-US-AndrewMultilingualNeural")
    a=p.parse_args()
    if not 4<=a.scenes<=48:
        p.error("Scene count must be 4–48")
    print("::group::RUN CONFIGURATION",flush=True)
    print(f"Format=Gemini decides | Scenes={a.scenes} | Voice={a.voice}",flush=True)
    print("Images: OVHcloud primary (up to 5 attempts), then AI Horde, Vexa and Pollinations fallbacks.",flush=True)
    print("Narration: Edge TTS | Rendering: FFmpeg | Delivery: GitHub Actions artifact",flush=True)
    print("::endgroup::",flush=True)
    OUT.mkdir(parents=True,exist_ok=True)

    package=None
    data=None
    for candidate in sorted((x for x in OUT.iterdir() if x.is_dir()),key=lambda x:x.name,reverse=True):
        story_file=candidate/"story.json"
        if not story_file.is_file():
            continue
        try:
            saved=json.loads(story_file.read_text(encoding="utf-8"))
            if saved.get("completed") is True:
                print(f"Skipping completed story package {candidate.name}.",flush=True)
                continue
            saved_scenes=saved.get("scenes")
            if (not isinstance(saved_scenes,list) or len(saved_scenes)!=a.scenes
                    or any(not isinstance(scene,dict) or scene.get("scene_number")!=i
                           or not str(scene.get("heading","")).strip()
                           or not str(scene.get("narration","")).strip()
                           or not str(scene.get("visual_description","")).strip()
                           or not str(scene.get("image_prompt","")).strip()
                           for i,scene in enumerate(saved_scenes,1))):
                continue
            package=candidate
            data=saved
            print(f"Resuming saved story package {candidate.name}.",flush=True)
            break
        except (OSError,ValueError,TypeError) as exc:
            print(f"Ignoring invalid story checkpoint {story_file}: {exc}",flush=True)

    if package is None:
        package=OUT/(time.strftime("%Y%m%d-%H%M%S",time.gmtime())+"-gemini")
        suffix=1
        while package.exists():
            package=OUT/(time.strftime("%Y%m%d-%H%M%S",time.gmtime())+f"-gemini-{suffix}")
            suffix+=1
        package.mkdir(parents=True)
        print("::group::STEP 1/5 - Gemini story planning",flush=True)
        data=plan_story(a.topic,a.scenes)
        data.update({"scene_count":a.scenes,"voice":a.voice,"completed":False})
        print("Gemini selected format: "+data["mode"],flush=True)
    else:
        data.setdefault("scene_count",a.scenes)
        data.setdefault("voice",a.voice)
        data.setdefault("completed",False)
        print("Reusing the saved story without asking Gemini to replace it.",flush=True)

    story_file=package/"story.json"
    temporary_story=story_file.with_name(story_file.name+".tmp")
    temporary_story.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary_story.replace(story_file)
    print(f"Story ready: {data['title']} | {len(data['scenes'])} scenes",flush=True)
    print("::endgroup::",flush=True)

    script="# "+data["title"]+"\n\n"+data["description"]+"\n\n"
    script+="\n\n".join(
        f"## Scene {scene['scene_number']}: {scene['heading']}\n\n"
        f"{scene['narration']}\n\n**Visual:** {scene['visual_description']}"
        for scene in data["scenes"]
    )
    (package/"script.md").write_text(script,encoding="utf-8")
    (package/"images").mkdir(exist_ok=True)
    print("::group::STEP 2/5 - Generate and validate scene images",flush=True)
    generate_all(data["scenes"],package/"images")
    print(f"All {len(data['scenes'])} scene images passed validation.",flush=True)
    print("::endgroup::",flush=True)

    print("::group::STEP 3/5 - Edge TTS narration and STEP 4/5 - FFmpeg rendering",flush=True)
    final=render(data["scenes"],package,str(data["voice"]))
    print("::endgroup::",flush=True)

    history_file=ROOT/"used_story_topics.json"
    history=json.loads(history_file.read_text(encoding="utf-8")) if history_file.is_file() else []
    if not isinstance(history,list):
        raise ValueError("used_story_topics.json must contain a JSON list")
    topic_key=" ".join(str(data["topic"]).casefold().split())
    existing={" ".join(str(item.get("topic","")).casefold().split())
              for item in history if isinstance(item,dict)}
    if topic_key not in existing:
        history.append({"title":data["title"],"topic":data["topic"],"description":data["description"]})
        temp_history=history_file.with_name(history_file.name+".tmp")
        temp_history.write_text(json.dumps(history,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temp_history.replace(history_file)
    print("Recorded completed topic history.",flush=True)
    print("STEP 5/5 - Package complete; artifact upload is the next GitHub Actions step.",flush=True)
    print("FINAL_VIDEO="+str(final))
    print("STORY_PACKAGE="+str(package))
if __name__=="__main__": main()

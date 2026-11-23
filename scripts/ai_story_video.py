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
OPENROUTER_KEY=os.getenv("OPENROUTER_API_KEY","").strip()
GROQ_MODEL=os.getenv("GROQ_MODEL","openai/gpt-oss-120b").strip()
KILO_API_KEY=os.getenv("KILO_API_KEY","").strip()
KILO_MODEL=os.getenv("KILO_MODEL","kilo-auto/free").strip()
KILO_FALLBACK_MODELS=[x.strip() for x in os.getenv("KILO_FALLBACK_MODELS","nvidia/nemotron-3.5-super-vl:free,dots-studio/dots-3-note-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free").split(",") if x.strip()]
OVH_API_KEY=os.getenv("OVH_AI_ENDPOINTS_API_KEY","").strip()
OVH_MODEL=os.getenv("OVH_MODEL","gpt-oss-20b").strip()
OVH_FALLBACK_MODELS=[x.strip() for x in os.getenv("OVH_FALLBACK_MODELS","gpt-oss-120b,Meta-Llama-3_3-70B-Instruct,Mistral-Small-3.2-24B-Instruct-2506").split(",") if x.strip()]
# Stable Gemini Developer API models, ordered with Flash-Lite first.
# Unknown/paid IDs are ignored so repository variables cannot silently select
# a model outside this known free-tier-compatible allowlist.
FREE_GEMINI_MODELS=(
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
)
_requested_model=os.getenv("GEMINI_MODEL","gemini-3.5-flash-lite").strip()
MODEL=_requested_model if _requested_model in FREE_GEMINI_MODELS else FREE_GEMINI_MODELS[0]
_requested_fallbacks=os.getenv(
    "GEMINI_FALLBACK_MODELS",
    ",".join(model for model in FREE_GEMINI_MODELS if model != MODEL),
)
FALLBACK=[
    model for model in (x.strip() for x in _requested_fallbacks.split(","))
    if model in FREE_GEMINI_MODELS and model != MODEL
]
# Always append every remaining allowlisted model so a partial Actions variable
# cannot accidentally disable the built-in failover chain.
FALLBACK=list(dict.fromkeys(FALLBACK + [
    model for model in FREE_GEMINI_MODELS if model != MODEL and model not in FALLBACK
]))
TIMEOUT=(20,180)
_OVH_LAST_CALL=0.0

def _retry_wait(response, attempt):
    """Honor provider Retry-After and use bounded exponential backoff."""
    retry_after=None
    if response is not None:
        try:
            retry_after=float(response.headers.get("Retry-After",""))
        except (TypeError,ValueError):
            retry_after=None
    delay=min(90,max(retry_after or 0,4*(2**(attempt-1))))
    print(f"Provider is busy or rate-limited; waiting {delay:.0f}s before retry.",flush=True)
    time.sleep(delay)

# Model catalogues are refreshed on every generator run. Catalogue discovery is
# free/read-only; the real story request doubles as the live availability test,
# avoiding extra billable "ping" generations.
GEMINI_CANDIDATES=list(dict.fromkeys([MODEL,*FALLBACK]))
KILO_CANDIDATES=["kilo-auto/free",*KILO_FALLBACK_MODELS]
OVH_CANDIDATES=list(dict.fromkeys([OVH_MODEL,*OVH_FALLBACK_MODELS]))
OPENROUTER_CANDIDATES=["openrouter/free"]
GROQ_CANDIDATES=[GROQ_MODEL]

def _is_zero_priced(entry):
    pricing=entry.get("pricing") or {}
    try:
        return (float(pricing.get("prompt",pricing.get("input",1)) or 0)==0
                and float(pricing.get("completion",pricing.get("output",1)) or 0)==0)
    except (TypeError,ValueError):
        return False

def refresh_model_catalogs():
    """Refresh public provider catalogues, keeping only suitable active/free candidates."""
    global GEMINI_CANDIDATES,KILO_CANDIDATES,OVH_CANDIDATES
    global OPENROUTER_CANDIDATES,GROQ_CANDIDATES
    print("::group::LIVE MODEL CATALOGUE REFRESH",flush=True)

    if KEY:
        try:
            response=requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                params={"key":KEY,"pageSize":1000},timeout=(5,20))
            response.raise_for_status()
            entries=response.json().get("models",[])
            found=[]
            for item in entries:
                if not isinstance(item,dict): continue
                methods=item.get("supportedGenerationMethods") or []
                name=str(item.get("name","")).replace("models/","",1)
                low=name.lower()
                if ("generateContent" not in methods or "flash" not in low
                        or any(x in low for x in ("tts","image","embedding","live","transcribe","robotics"))):
                    continue
                found.append(name)
            def gemini_rank(name):
                nums=tuple(int(x) for x in re.findall(r"\d+",name))
                return (0 if "flash-lite" in name.lower() else 1,
                        1 if "preview" in name.lower() else 0,
                        tuple(-x for x in nums),name)
            found=sorted(set(found),key=gemini_rank)
            GEMINI_CANDIDATES=found[:6]
            print(f"Gemini catalogue: {len(found)} text Flash models; priority={GEMINI_CANDIDATES[:5]}",flush=True)
        except Exception as exc:
            print(f"Gemini catalogue refresh failed; retaining configured candidates: {exc}",flush=True)
    else:
        print("Gemini catalogue skipped: GEMINI_API_KEY missing.",flush=True)

    try:
        response=requests.get("https://ai-gateway.kilo.ai/api/v1/models",timeout=(5,20))
        response.raise_for_status()
        entries=response.json().get("data",[])
        free=["kilo-auto/free"]
        for item in entries if isinstance(entries,list) else []:
            if not isinstance(item,dict) or not isinstance(item.get("id"),str): continue
            model_id=item["id"]
            if any(token in model_id.lower() for token in ("embed","rerank","tts","image","transcribe")): continue
            if _is_zero_priced(item) or model_id.endswith(":free"):
                free.append(model_id)
        KILO_CANDIDATES=list(dict.fromkeys(free))[:9]
        print(f"Kilo catalogue: {len(KILO_CANDIDATES)} free routes found.",flush=True)
    except Exception as exc:
        print(f"Kilo catalogue refresh failed; retaining safe defaults: {exc}",flush=True)

    try:
        response=requests.get("https://catalog.endpoints.ai.ovh.net/rest/v1/models_v2",timeout=(5,20))
        response.raise_for_status()
        payload=response.json()
        entries=payload if isinstance(payload,list) else payload.get("data",[])
        active=[]
        for item in entries:
            if not isinstance(item,dict) or item.get("available") is not True: continue
            model_id=item.get("id")
            if not isinstance(model_id,str): continue
            metadata=item.get("metadata") or {}
            specs=(metadata.get("model_specs") or {})
            capabilities=specs.get("capabilities") or {}
            output=capabilities.get("output_modality") or []
            if isinstance(output,str): output=[output]
            if output and not any("text" in str(x).lower() for x in output): continue
            if model_id in OVH_CANDIDATES or _is_zero_priced(metadata.get("usage_information",{})):
                active.append(model_id)
        OVH_CANDIDATES=list(dict.fromkeys(
            [m for m in OVH_CANDIDATES if m in active]+active
        ))[:3]
        print(f"OVHcloud catalogue: {len(active)} active text/free candidates; selected={OVH_CANDIDATES[:5]}",flush=True)
    except Exception as exc:
        print(f"OVHcloud catalogue refresh failed; retaining configured candidates: {exc}",flush=True)

    if OPENROUTER_KEY:
        try:
            response=requests.get("https://openrouter.ai/api/v1/models",
                params={"output_modalities":"text"},
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}"},timeout=(5,20))
            response.raise_for_status()
            entries=response.json().get("data",[])
            free=["openrouter/free"]
            for item in entries if isinstance(entries,list) else []:
                if isinstance(item,dict) and isinstance(item.get("id"),str):
                    if item["id"].endswith(":free") or _is_zero_priced(item):
                        free.append(item["id"])
            OPENROUTER_CANDIDATES=list(dict.fromkeys(free))[:9]
            print(f"OpenRouter catalogue: {len(OPENROUTER_CANDIDATES)} free routes found.",flush=True)
        except Exception as exc:
            print(f"OpenRouter catalogue refresh failed; retaining free router: {exc}",flush=True)
    else:
        print("OpenRouter catalogue skipped: OPENROUTER_API_KEY missing.",flush=True)

    if GROQ_KEY:
        try:
            response=requests.get("https://api.groq.com/openai/v1/models",
                headers={"Authorization":f"Bearer {GROQ_KEY}"},timeout=(5,20))
            response.raise_for_status()
            entries=response.json().get("data",[])
            available={item.get("id") for item in entries if isinstance(item,dict)
                       and item.get("active",True) is not False and isinstance(item.get("id"),str)
                       and not any(token in item.get("id","").lower()
                                   for token in ("whisper","speech","guard","embedding","playai"))}
            GROQ_CANDIDATES=sorted(available)
            if GROQ_MODEL in GROQ_CANDIDATES:
                GROQ_CANDIDATES.remove(GROQ_MODEL)
                GROQ_CANDIDATES.insert(0,GROQ_MODEL)
            print(f"Groq catalogue: {len(GROQ_CANDIDATES)} active model IDs discovered.",flush=True)
        except Exception as exc:
            print(f"Groq catalogue refresh failed; retaining configured choice: {exc}",flush=True)
    else:
        print("Groq catalogue skipped: GROQ_API_KEY missing.",flush=True)

    # Persist the latest catalogue for every story generator in this repository.
    # Only write after a successful refresh cycle; each provider retains its
    # configured safe candidates when its catalogue endpoint is unavailable.
    registry_path=ROOT/"story-model-registry.json"
    registry={"updated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
              "providers":{
                  "Gemini":GEMINI_CANDIDATES,
                  "OVH":OVH_CANDIDATES,
                  "Kilo":KILO_CANDIDATES,
                  "OpenRouter":OPENROUTER_CANDIDATES,
                  "Groq":GROQ_CANDIDATES,
              }}
    temporary=registry_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(registry_path)
    print(f"Shared model registry updated: {registry_path.name}",flush=True)
    print("::endgroup::",flush=True)

def parse_json(raw):
    """Parse a full JSON object, or recover complete scenes from a truncated story."""
    fence=chr(96)*3
    raw=str(raw or "").strip()
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
            if depth==0:
                try:
                    return json.loads(raw[start:i+1])
                except json.JSONDecodeError:
                    break

    decoder=json.JSONDecoder()
    recovered={}
    for field in ("mode","title","topic","description","visual_style","continuity_bible"):
        match=re.search(r'"'+field+r'"\s*:\s*',raw)
        if match:
            try:
                recovered[field],_=decoder.raw_decode(raw,match.end())
            except (ValueError,json.JSONDecodeError):
                pass
    scene_match=re.search(r'"scenes"\s*:\s*\[',raw)
    if scene_match:
        cursor=scene_match.end()
        scenes=[]
        while cursor<len(raw):
            while cursor<len(raw) and (raw[cursor].isspace() or raw[cursor]==","):
                cursor+=1
            if cursor>=len(raw) or raw[cursor]=="]":
                break
            try:
                item,next_cursor=decoder.raw_decode(raw,cursor)
            except (ValueError,json.JSONDecodeError):
                break
            if not isinstance(item,dict):
                break
            scenes.append(item)
            cursor=next_cursor
        if scenes:
            recovered["scenes"]=scenes
            print(
                f"Recovered {len(scenes)} complete scenes from a truncated planner response; "
                "the missing scenes will be regenerated.",
                flush=True,
            )
            return recovered
    raise ValueError("LLM returned malformed or incomplete JSON without recoverable scenes")


def repair_story_scenes(story,count):
    """Generate missing scenes in small batches while retaining valid scenes."""
    scenes=story.get("scenes")
    if not isinstance(scenes,list):
        scenes=[]
    if len(scenes)>count:
        del scenes[count:]
    batch=0
    while len(scenes)<count:
        batch+=1
        needed=min(6,count-len(scenes))
        prompt=f"""
Continue this exact story. Do not change its topic, format, characters, style or established facts.
Mode: {story.get("mode","science")}
Title: {story.get("title","")}
Topic: {story.get("topic","")}
Description: {story.get("description","")}
Visual style: {story.get("visual_style","")}
Continuity bible: {story.get("continuity_bible","")}
The story already contains {len(scenes)} complete scenes. Create exactly {needed} NEW scenes, numbered {len(scenes)+1} through {len(scenes)+needed}.
The last existing scenes are:
{json.dumps(scenes[-4:],ensure_ascii=False)}
Return JSON only in this shape:
{{"scenes":[{{"scene_number":{len(scenes)+1},"heading":"short heading","narration":"2-4 natural spoken sentences","visual_description":"concrete visible action and composition","image_prompt":"standalone detailed polished 3D CGI image prompt; specify camera, composition, lighting, materials, depth and 16:9; no text, logo or watermark"}}]}}
Every field must be non-empty. Preserve continuity, avoid repeating prior scenes and move the story forward. Finish the story with a memorable conclusion in the final batch.
"""
        added=False
        for attempt in range(1,4):
            try:
                result=gemini(prompt)
                new_scenes=result.get("scenes",[])
                if not isinstance(new_scenes,list):
                    raise ValueError("scene repair response has no scenes array")
                accepted=[]
                for item in new_scenes:
                    if not isinstance(item,dict):
                        continue
                    if not all(isinstance(item.get(key),str) and item[key].strip()
                               for key in ("heading","narration","image_prompt")):
                        continue
                    if not isinstance(item.get("visual_description"),str) or not item["visual_description"].strip():
                        item["visual_description"]=item["image_prompt"].strip()
                    accepted.append(item)
                if not accepted:
                    raise ValueError("scene repair returned no complete scenes")
                for item in accepted[:needed]:
                    item["scene_number"]=len(scenes)+1
                    scenes.append(item)
                story["scenes"]=scenes
                print(
                    f"Scene repair batch {batch}: added {min(len(accepted),needed)}; "
                    f"{len(scenes)}/{count} scenes complete.",
                    flush=True,
                )
                added=True
                break
            except Exception as exc:
                print(
                    f"Scene repair batch {batch}, attempt {attempt}/3 failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                if attempt<3:
                    time.sleep(attempt*4)
        if not added:
            raise RuntimeError(
                f"Could not repair story to {count} scenes; {len(scenes)} valid scenes are retained."
            )
    return scenes

def gemini(prompt):
    errors=[]
    if KEY:
        # Try the configured primary, then every allowed fallback in order.
        for model in GEMINI_CANDIDATES:
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            model_failed=False
            for attempt in range(1,4):
                try:
                    r=requests.post(
                        url,
                        params={"key":KEY},
                        json={"contents":[{"parts":[{"text":prompt}]}],
                              "generationConfig":{"responseMimeType":"application/json","temperature":0.8}},
                        timeout=(3,18),
                    )
                    if r.status_code in (400,403,404):
                        error=f"Gemini {model} unavailable/rejected (HTTP {r.status_code}): {r.text[:900]}"
                        errors.append(error)
                        print(error,flush=True)
                        model_failed=True
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
                        _retry_wait(locals().get("r"),attempt)
                    else:
                        model_failed=True
            if model_failed:
                print(f"Moving to next Gemini model after {model} failed.",flush=True)
    else:
        errors.append("GEMINI_API_KEY is not configured; skipped Gemini.")
        print("Gemini skipped: GEMINI_API_KEY is not configured.",flush=True)

    # OVHcloud AI Endpoints: documented OpenAI-compatible chat completions API.
    global _OVH_LAST_CALL
    ovh_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
    ovh_errors=[]
    ovh_models=OVH_CANDIDATES
    ovh_headers={"Content-Type":"application/json"}
    if OVH_API_KEY:
        ovh_headers["Authorization"]=f"Bearer {OVH_API_KEY}"
    else:
        print("OVH_AI_ENDPOINTS_API_KEY is not configured; trying anonymous OVH access.",flush=True)
    for ovh_model in ovh_models:
        for attempt in range(1,4):
            response=None
            try:
                if _OVH_LAST_CALL:
                    wait=max(0,31-(time.monotonic()-_OVH_LAST_CALL))
                    if wait: time.sleep(wait)
                _OVH_LAST_CALL=time.monotonic()
                response=requests.post(ovh_url,headers=ovh_headers,
                    json={"model":ovh_model,"messages":[
                        {"role":"system","content":"Return only one valid JSON object matching the requested schema. No Markdown fences or commentary."},
                        {"role":"user","content":prompt}], "temperature":0.8,"max_tokens":16384},timeout=(5,90))
                if response.status_code in (400,401,403,404,422):
                    error=f"OVHcloud {ovh_model} HTTP {response.status_code}: {response.text[:900]}"
                    ovh_errors.append(error); print(error,flush=True); break
                if response.status_code in (408,425,429,500,502,503,504):
                    raise RuntimeError(f"OVHcloud HTTP {response.status_code}: {response.text[:900]}")
                response.raise_for_status()
                choices=response.json().get("choices") or []
                message=choices[0].get("message",{}) if choices else {}
                content=message.get("content","")
                if isinstance(content,list): content="".join(part.get("text","") for part in content if isinstance(part,dict))
                result=parse_json(content)
                print(f"OVHcloud planner active: {ovh_model}",flush=True)
                return result
            except Exception as exc:
                ovh_errors.append(f"{ovh_model} try {attempt}/3: {type(exc).__name__}: {exc}")
                print(f"OVHcloud {ovh_model} attempt {attempt}/3 failed: {type(exc).__name__}: {exc}",flush=True)
                if attempt<3: _retry_wait(response,attempt)
    # Kilo Gateway: discover the live catalogue and try catalogue-confirmed free models.
    kilo_url="https://ai-gateway.kilo.ai/api/v1/chat/completions"
    kilo_errors=[]
    kilo_headers={"Content-Type":"application/json"}
    if KILO_API_KEY: kilo_headers["Authorization"]=f"Bearer {KILO_API_KEY}"
    kilo_candidates=KILO_CANDIDATES
    messages=[
        {"role":"system","content":"Return only one valid JSON object matching the requested schema. No Markdown fences or commentary."},
        {"role":"user","content":prompt},
    ]
    for kilo_model in kilo_candidates:
        for attempt in range(1,4):
            try:
                response=requests.post(kilo_url,headers=kilo_headers,
                    json={"model":kilo_model,"messages":messages,"max_tokens":16384},timeout=(5,90))
                if response.status_code in (400,401,403,404,422):
                    error=f"Kilo {kilo_model} HTTP {response.status_code}: {response.text[:900]}"
                    kilo_errors.append(error); print(error,flush=True); break
                if response.status_code in (408,425,429,500,502,503,504):
                    raise RuntimeError(f"Kilo HTTP {response.status_code}: {response.text[:900]}")
                response.raise_for_status()
                choices=response.json().get("choices") or []
                message=choices[0].get("message",{}) if choices else {}
                content=message.get("content","")
                if isinstance(content,list): content="".join(part.get("text","") for part in content if isinstance(part,dict))
                result=parse_json(content)
                print(f"Kilo planner active: {kilo_model}",flush=True)
                return result
            except Exception as exc:
                kilo_errors.append(f"{kilo_model} try {attempt}/2: {type(exc).__name__}: {exc}")
                print(f"Kilo {kilo_model} attempt {attempt}/2 failed: {exc}",flush=True)
                if attempt<3: _retry_wait(locals().get("response"),attempt)
    if not kilo_candidates: kilo_errors.append("No Kilo free models found in live catalogue.")
    if OPENROUTER_KEY:
        for or_model in OPENROUTER_CANDIDATES:
            for attempt in range(1,4):
                response=None
                try:
                    response=requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json",
                                 "HTTP-Referer":"https://github.com/manojkumar166-png/stickman-lab",
                                 "X-Title":"AI Story Science Video"},
                        json={"model":or_model,"messages":[
                            {"role":"system","content":"Return one complete valid JSON object matching the requested schema. No Markdown or commentary."},
                            {"role":"user","content":prompt}],"max_tokens":16000},
                        timeout=(5,60))
                    if response.status_code in (400,401,403,404,422):
                        raise PermanentProviderError(f"OpenRouter {or_model} HTTP {response.status_code}: {response.text[:800]}")
                    if response.status_code in (408,425,429,500,502,503,504):
                        raise RuntimeError(f"OpenRouter {or_model} HTTP {response.status_code}: {response.text[:800]}")
                    response.raise_for_status()
                    choices=response.json().get("choices") or []
                    content=choices[0].get("message",{}).get("content","") if choices else ""
                    result=parse_json(content)
                    print(f"OpenRouter free planner fallback active: {or_model}.",flush=True)
                    return result
                except Exception as exc:
                    print(f"OpenRouter {or_model} attempt {attempt}/3 failed: {type(exc).__name__}: {exc}",flush=True)
                    if attempt<3: _retry_wait(response,attempt)
    else:
        print("OpenRouter skipped: OPENROUTER_API_KEY is not configured.",flush=True)

    # Groq provides another independently hosted model fallback.
    groq_errors=[]
    if GROQ_KEY:
        groq_url="https://api.groq.com/openai/v1/chat/completions"
        for groq_model in GROQ_CANDIDATES:
            for attempt in range(1,4):
                response=None
                try:
                    response=requests.post(groq_url,
                        headers={"Authorization":f"Bearer {GROQ_KEY}","Content-Type":"application/json"},
                        json={"model":groq_model,"messages":[
                            {"role":"system","content":"Return only a valid JSON object matching the user's requested schema. Follow all instructions precisely."},
                            {"role":"user","content":prompt}],
                            "response_format":{"type":"json_object"},"temperature":0.8,"max_completion_tokens":32768},
                        timeout=(5,60))
                    if response.status_code in (400,401,403,404,422):
                        raise PermanentProviderError(f"Groq {groq_model} HTTP {response.status_code}: {response.text[:500]}")
                    if response.status_code in (408,425,429,500,502,503,504):
                        raise RuntimeError(f"Groq {groq_model} HTTP {response.status_code}: {response.text[:500]}")
                    response.raise_for_status()
                    choices=response.json().get("choices") or []
                    content=choices[0].get("message",{}).get("content","") if choices else ""
                    result=parse_json(content)
                    print(f"Open-weight planner backup active: Groq {groq_model}",flush=True)
                    return result
                except Exception as exc:
                    groq_errors.append(f"{groq_model} try {attempt}/3: {type(exc).__name__}: {exc}")
                    print(f"Groq {groq_model} attempt {attempt}/3 failed: {type(exc).__name__}: {exc}",flush=True)
                    if attempt<3: _retry_wait(response,attempt)
    else:
        print("Groq skipped: GROQ_API_KEY is not configured.",flush=True)

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
    normalize=lambda value: re.sub(r"[^a-z0-9]+"," ",str(value).casefold()).strip()
    used_core={normalize(item.get("topic","")) for item in used_topics if item.get("topic")}
    rejected_topics=[]
    data=None
    # A duplicate is a content-selection issue, not a reason to fail the whole
    # workflow. Ask the planner again, explicitly excluding each rejected topic.
    for topic_attempt in range(1,4):
        candidate=gemini(prompt)
        if not isinstance(candidate,dict):
            raise ValueError("Planner returned a non-object response.")
        candidate_topic=str(candidate.get("topic") or candidate.get("title") or "").strip()
        if normalize(candidate_topic) in used_core:
            rejected_topics.append(candidate_topic)
            print(
                f"Planner chose a previously used topic (attempt {topic_attempt}/3): "
                f"{candidate_topic!r}. Requesting a genuinely different subject.",
                flush=True,
            )
            if topic_attempt==3:
                raise ValueError(
                    "Planner selected previously used core topics after 3 attempts: "
                    + "; ".join(rejected_topics)
                )
            prompt += (
                "\\n\\nTOPIC REJECTION — IMPORTANT: Your previous response selected a "
                "previously used topic. Do NOT use or rephrase any of these rejected topics:\\n"
                + "\\n".join("- "+item for item in rejected_topics)
                + "\\nChoose a different underlying phenomenon, mechanism, question, or story premise. "
                  "Return a completely new title, topic, and story."
            )
            continue
        data=candidate
        break
    if data is None:
        raise RuntimeError("Planner could not select a fresh topic.")
    if not data.get("topic") and data.get("title"):
        data["topic"]=data["title"]
    if not data.get("title") and data.get("topic"):
        data["title"]=str(data["topic"])[:100]
    if not data.get("topic") or not data.get("title"):
        raise ValueError("Planner response did not contain a usable title/topic.")
    if data.get("mode") not in ("science","animated"):
        data["mode"]="science"
        print("Planner omitted the format; defaulting safely to science documentary.",flush=True)
    data.setdefault("description",f"An accessible exploration of {data['topic']}.")
    data.setdefault("visual_style","Polished cinematic 3D CGI with consistent lighting, materials and depth.")
    data.setdefault("continuity_bible","Maintain a consistent visual style and continuity throughout every scene.")
    scenes=repair_story_scenes(data,count)
    if not isinstance(scenes,list) or len(scenes)!=count:
        raise ValueError(f"Expected exactly {count} scenes after repair; got {len(scenes) if isinstance(scenes,list) else 'invalid'}.")
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
    if normalize(data["title"]) in {normalize(item) for item in topic_examples}:
        raise ValueError("Gemini copied a title from topics.txt instead of inventing a new topic.")
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
    """Generate one scene's narration with male Edge Neural voice and Google fallback."""
    text=str(text or "").strip()
    if not text:
        raise ValueError("Scene narration is empty.")
    voice=str(voice or "en-US-AndrewMultilingualNeural")
    last=None
    for attempt in range(1,6):
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.unlink(missing_ok=True)
            await asyncio.wait_for(
                edge_tts.Communicate(text=text,voice=voice,rate="+0%").save(str(path)),
                timeout=240,
            )
            if not path.is_file() or path.stat().st_size<=1000:
                raise RuntimeError("Edge TTS returned an empty or incomplete audio file.")
            if not media_has_stream(path,"a:0",1000):
                raise RuntimeError("Edge TTS output failed ffprobe audio-stream validation.")
            print(f"Edge TTS narration validated with {voice} ({path.stat().st_size} bytes).",flush=True)
            return
        except Exception as exc:
            last=exc
            path.unlink(missing_ok=True)
            if attempt<5:
                delay=min(30,2**attempt)
                print(
                    f"Edge TTS attempt {attempt}/5 failed: {type(exc).__name__}: {exc}; "
                    f"retrying in {delay}s.",
                    file=sys.stderr,flush=True,
                )
                await asyncio.sleep(delay)

    print(
        f"Edge TTS failed after 5 attempts ({last}); switching to Google TTS fallback.",
        file=sys.stderr,flush=True,
    )
    fallback_error=None
    for attempt in range(1,4):
        try:
            path.unlink(missing_ok=True)
            gTTS(text=text,lang="en",slow=False,timeout=(15,90)).save(str(path))
            if not path.is_file() or path.stat().st_size<=1000:
                raise RuntimeError("Google TTS returned an empty or incomplete audio file.")
            if not media_has_stream(path,"a:0",1000):
                raise RuntimeError("Google TTS output failed ffprobe audio-stream validation.")
            print(f"Google TTS fallback validated ({path.stat().st_size} bytes; attempt {attempt}/3).",flush=True)
            return
        except Exception as exc:
            fallback_error=exc
            path.unlink(missing_ok=True)
            if attempt<3:
                delay=attempt*5
                print(
                    f"Google TTS attempt {attempt}/3 failed: {type(exc).__name__}: {exc}; "
                    f"retrying in {delay}s.",
                    file=sys.stderr,flush=True,
                )
                await asyncio.sleep(delay)
    raise RuntimeError(
        f"Edge TTS failed after 5 attempts ({last}); Google TTS failed after 3 attempts "
        f"({fallback_error})."
    ) from fallback_error


def command(args):
    """Run FFmpeg with retries and expose useful diagnostics instead of hiding stderr."""
    last_error = None
    for attempt in range(1, 4):
        try:
            result = subprocess.run(
                args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, timeout=900,
            )
            if result.stderr.strip():
                print("FFmpeg notice: " + result.stderr.strip()[-2000:], file=sys.stderr, flush=True)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            last_error = exc
            detail = getattr(exc, "stderr", None) or ""
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", errors="replace")
            print(
                f"FFmpeg attempt {attempt}/3 failed: {exc}\n{str(detail)[-4000:]}",
                file=sys.stderr, flush=True,
            )
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
        print("FFmpeg H.264 failed after 3 attempts; trying MPEG-4 encoder fallback.", flush=True)
        try:
            result = subprocess.run(
                fallback, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, timeout=900,
            )
            if result.stderr.strip():
                print("FFmpeg fallback notice: " + result.stderr.strip()[-2000:], file=sys.stderr, flush=True)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = getattr(exc, "stderr", None) or ""
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FFmpeg MPEG-4 fallback also failed: {exc}\n{str(detail)[-4000:]}"
            ) from exc
    detail = getattr(last_error, "stderr", None) or ""
    if isinstance(detail, bytes):
        detail = detail.decode("utf-8", errors="replace")
    raise RuntimeError(
        f"FFmpeg failed after 3 attempts: {last_error}\n{str(detail)[-4000:]}"
    ) from last_error


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


def media_is_valid(path, decode=False):
    """Require both streams, a real duration, and optionally a full decode pass."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 2048:
        return False
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if probe.returncode != 0:
            print(f"ffprobe rejected {path.name}: {probe.stderr[-1500:]}", file=sys.stderr, flush=True)
            return False
        metadata = json.loads(probe.stdout or "{}")
        stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
        duration = float((metadata.get("format") or {}).get("duration") or 0)
        if not {"video", "audio"}.issubset(stream_types) or duration <= 0.05:
            print(
                f"Media validation failed for {path.name}: streams={sorted(stream_types)}, duration={duration:.3f}s",
                file=sys.stderr, flush=True,
            )
            return False
        if decode:
            decoded = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
                capture_output=True, text=True, timeout=900,
            )
            if decoded.returncode != 0:
                print(
                    f"Decode validation failed for {path.name}: {decoded.stderr[-2500:]}",
                    file=sys.stderr, flush=True,
                )
                return False
        return True
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Media validation error for {path.name}: {exc}", file=sys.stderr, flush=True)
        return False


def prepare_audio(scenes,package,voice):
    """Prepare and validate the scene narration and image assets for Remotion."""
    aud=package/"audio"
    aud.mkdir(parents=True,exist_ok=True)
    for s in scenes:
        n=s["scene_number"]
        audio=aud/f"scene-{n:02d}.mp3"
        image=package/"images"/f"scene-{n:02d}.png"
        if not image.is_file():
            raise FileNotFoundError(f"Scene {n}: generated image checkpoint is missing: {image}")
        try:
            with Image.open(image) as im:
                im.verify()
        except Exception as exc:
            raise RuntimeError(f"Scene {n}: saved image is corrupt; refusing to render: {exc}") from exc
        if not media_has_stream(audio,"a:0",1000):
            audio.unlink(missing_ok=True)
            print(f"Edge TTS: scene {n}/{len(scenes)}",flush=True)
            asyncio.run(speak(s["narration"],audio,voice))
        else:
            print(f"Edge TTS: reusing saved audio for scene {n}/{len(scenes)}",flush=True)
        if not media_has_stream(audio,"a:0",1000):
            raise RuntimeError(f"Scene {n}: generated narration failed media validation")
    print(f"Prepared {len(scenes)} validated image/audio scene pairs for Remotion.",flush=True)


def render(scenes,package,voice):
    aud=package/"audio"
    seg=package/"segments"
    aud.mkdir(parents=True,exist_ok=True)
    seg.mkdir(parents=True,exist_ok=True)
    parts=[]
    for s in scenes:
        n=s["scene_number"]
        audio=aud/f"scene-{n:02d}.mp3"
        image=package/"images"/f"scene-{n:02d}.png"
        video=seg/f"segment-{n:02d}.mp4"
        if not media_has_stream(audio,"a:0",1000):
            audio.unlink(missing_ok=True)
            print(f"Edge TTS: scene {n}/{len(scenes)}",flush=True)
            asyncio.run(speak(s["narration"],audio,voice))
            if not media_has_stream(audio,"a:0",1000):
                raise RuntimeError(f"Scene {n}: generated narration failed media validation")
        else:
            print(f"Edge TTS: reusing saved audio for scene {n}/{len(scenes)}",flush=True)

        if not image.is_file():
            raise FileNotFoundError(f"Scene {n}: generated image checkpoint is missing: {image}")
        try:
            with Image.open(image) as im:
                im.verify()
        except Exception as exc:
            raise RuntimeError(f"Scene {n}: saved image is corrupt; refusing to render: {exc}") from exc

        if not media_is_valid(video, decode=True):
            if video.exists():
                print(f"Scene {n}: discarding invalid/partial segment and rebuilding from saved inputs.", flush=True)
            video.unlink(missing_ok=True)
            temporary = video.with_name(video.stem + ".rendering.mp4")
            last_error = None
            for encoder in ("libx264", "mpeg4"):
                temporary.unlink(missing_ok=True)
                print(
                    f"FFmpeg: rendering scene {n}/{len(scenes)} with {encoder}; "
                    "saved image and narration will be reused.",
                    flush=True,
                )
                args = [
                    "ffmpeg", "-hide_banner", "-y", "-loop", "1", "-framerate", "25",
                    "-i", str(image), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                    "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,format=yuv420p",
                    "-r", "25", "-c:v", encoder,
                ]
                if encoder == "libx264":
                    args.extend(["-preset", "veryfast", "-tune", "stillimage", "-crf", "20"])
                else:
                    args.extend(["-q:v", "5"])
                args.extend([
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", "-max_muxing_queue_size", "1024",
                    "-movflags", "+faststart", str(temporary),
                ])
                try:
                    command(args)
                    if not media_is_valid(temporary, decode=True):
                        raise RuntimeError(f"{encoder} output failed stream/duration/full-decode validation")
                    temporary.replace(video)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    temporary.unlink(missing_ok=True)
                    print(
                        f"Scene {n}: {encoder} render attempt failed: {type(exc).__name__}: {exc}",
                        file=sys.stderr, flush=True,
                    )
            if last_error is not None:
                raise RuntimeError(
                    f"Scene {n}: could not render from the preserved image/audio checkpoints "
                    f"with H.264 or MPEG-4: {last_error}"
                ) from last_error
        else:
            print(f"FFmpeg: reusing fully decoded segment for scene {n}/{len(scenes)}",flush=True)
        parts.append(video)

    concat=package/"concat.txt"
    concat.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts),encoding="utf-8")
    final=package/"final-video.mp4"
    if not media_is_valid(final, decode=True):
        final.unlink(missing_ok=True)
        temporary_final = final.with_name(final.stem + ".rendering.mp4")
        temporary_final.unlink(missing_ok=True)
        try:
            command([
                "ffmpeg","-hide_banner","-y","-f","concat","-safe","0","-i",str(concat),
                "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
                "-c:a","aac","-b:a","128k","-movflags","+faststart",str(temporary_final),
            ])
            if not media_is_valid(temporary_final, decode=True):
                raise RuntimeError("Final video failed stream/duration/full-decode validation")
            temporary_final.replace(final)
        except Exception:
            temporary_final.unlink(missing_ok=True)
            raise
    return final

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--topic",default="")
    p.add_argument("--scenes",type=int,default=8)
    p.add_argument("--voice",default="en-US-AndrewMultilingualNeural")
    p.add_argument("--skip-render",action="store_true",help="Prepare scene assets for an external renderer such as Remotion.")
    a=p.parse_args()
    if not 4<=a.scenes<=48:
        p.error("Scene count must be 4–48")
    refresh_model_catalogs()
    print("::group::RUN CONFIGURATION",flush=True)
    print(f"Format=Gemini decides | Scenes={a.scenes} | Voice={a.voice}",flush=True)
    print("Images: OVHcloud primary (up to 5 attempts), then AI Horde, Vexa and Pollinations fallbacks.",flush=True)
    print("Narration: male Edge Neural voice with retried Google TTS fallback | Rendering: FFmpeg | Delivery: GitHub Actions artifact",flush=True)
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
        data.setdefault("completed",False)
        print("Reusing the saved story without asking Gemini to replace it.",flush=True)

    # The selected workflow voice is authoritative, including when resuming an
    # older checkpoint that may have stored a different narrator.
    data["voice"]=a.voice or "en-US-AndrewMultilingualNeural"

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
    if a.skip_render:
        prepare_audio(data["scenes"],package,str(data["voice"]))
        final=package/"final-video.mp4"
        print("Remotion rendering is delegated to the AI Story workflow.",flush=True)
    else:
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

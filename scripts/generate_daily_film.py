#!/usr/bin/env python3
"""Generate a fresh nine-shot daily stickman film brief with Gemini."""
import argparse, datetime as dt, json, os, re
from pathlib import Path
import requests

ROOT=Path("stickman-films"); LATEST=ROOT/"latest"; HISTORY=ROOT/"topic-history.json"
MODEL=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
TIMELINE=[(0,3),(3,5),(5,8),(8,11),(11,14),(14,18),(18,22),(22,27),(27,30)]
VISUALS=["door","phone","umbrella","plant","clock","book","cup","star","planet","tree","animal","train","bridge","cloud","heart","lightbulb"]
EMOTIONS=["neutral","curious","worried","happy","sad","surprised"]; SOUNDS=["tap","whoosh","chime","thud","none"]
CATEGORIES=["space and astronomy","Earth, oceans and weather","animals and nature","human body and senses","brain, memory and behavior","physics and everyday science","technology and engineering","history-changing inventions","kindness and human connection","mysteries of the natural world","time, energy and the universe"]

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--topic",default=""); args=parser.parse_args()
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key: raise SystemExit("GEMINI_API_KEY is missing. Add it in repository Settings > Secrets and variables > Actions.")
    ROOT.mkdir(exist_ok=True); LATEST.mkdir(exist_ok=True)
    history=json.loads(HISTORY.read_text()) if HISTORY.exists() else {"used_titles":[],"films":[]}
    recent=history.get("used_titles",[]); category=CATEGORIES[dt.date.today().toordinal()%len(CATEGORIES)]
    schema={"type":"OBJECT","properties":{
      "title":{"type":"STRING"},"premise":{"type":"STRING"},"end_card":{"type":"STRING"},
      "scenes":{"type":"ARRAY","minItems":9,"maxItems":9,"items":{"type":"OBJECT","properties":{
        "title":{"type":"STRING"},"action":{"type":"STRING"},"camera":{"type":"STRING"},
        "visual":{"type":"STRING","enum":VISUALS},"emotion":{"type":"STRING","enum":EMOTIONS},
        "sound":{"type":"STRING","enum":SOUNDS}},
        "required":["title","action","camera","visual","emotion","sound"]}}},
      "required":["title","premise","end_card","scenes"]}
    subject=("Make the story about this topic: "+args.topic) if args.topic else ("Choose a fresh topic in "+category)
    prompt=f"""Create an original, family-friendly, emotionally engaging 30-second 2D stickman short.
{subject}. Avoid these recent titles: {json.dumps(recent[-100:])}.
The same friendly hero appears throughout: coral hoodie, cream round face, dark trousers.
Return exactly 9 chronological scenes, with time slots 0-3, 3-5, 5-8, 8-11, 11-14, 14-18, 18-22, 22-27, 27-30 seconds. Beats: establish, inciting event, approach, discovery, reveal, emotional turn, decision, action, payoff.
Keep actions concrete and drawable. visual must be one of {", ".join(VISUALS)}. title under 5 words; action under 24 words; camera under 8 words. Use no dialogue, voiceover, music, copyrighted characters or real-person likenesses. Sound effects only. End card maximum 8 words. Return JSON only."""
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    film=None; last=None
    for attempt in range(3):
      try:
        response=requests.post(url,params={"key":key},json={"contents":[{"parts":[{"text":prompt}]}],
          "generationConfig":{"temperature":0.9,"responseMimeType":"application/json","responseSchema":schema}},timeout=90)
        if not response.ok: raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:800]}")
        payload=response.json(); candidates=payload.get("candidates") or []
        if not candidates: raise ValueError("Gemini returned no candidates")
        raw="".join(p.get("text","") for p in candidates[0].get("content",{}).get("parts",[]) if isinstance(p,dict))
        data=json.loads(raw)
        if not isinstance(data,dict): raise ValueError("Gemini response is not an object")
        for field,limit in [("title",90),("premise",420),("end_card",70)]:
          val=data.get(field)
          if not isinstance(val,str) or not val.strip() or len(val)>limit: raise ValueError("Invalid "+field)
          data[field]=val.strip()
        scenes=data.get("scenes")
        if not isinstance(scenes,list) or len(scenes)!=9: raise ValueError("Expected exactly 9 scenes")
        clean=[]
        for i,(scene,(start,end)) in enumerate(zip(scenes,TIMELINE),1):
          if not isinstance(scene,dict): raise ValueError("Invalid scene "+str(i))
          def txt(k,n):
            v=scene.get(k)
            if not isinstance(v,str) or not v.strip() or len(v)>n: raise ValueError("Invalid scene "+str(i)+" "+k)
            return v.strip()
          if scene.get("visual") not in VISUALS or scene.get("emotion") not in EMOTIONS or scene.get("sound") not in SOUNDS: raise ValueError("Unsupported scene enum")
          clean.append({"n":i,"start":start,"end":end,"title":txt("title",48),"action":txt("action",180),"camera":txt("camera",64),"visual":scene["visual"],"emotion":scene["emotion"],"sound":scene["sound"]})
        norm=re.sub(r"\s+"," ",data["title"].casefold()).strip()
        if norm in {re.sub(r"\s+"," ",str(x).casefold()).strip() for x in recent}: raise ValueError("Repeated title")
        data.update({"scenes":clean,"date":dt.date.today().isoformat(),"duration":30,"fps":30,"width":1920,"height":1080,"voiceover":False,"music":False})
        film=data; break
      except Exception as exc:
        last=exc; print(f"Gemini attempt {attempt+1}/3 failed: {type(exc).__name__}: {exc}",flush=True)
    if film is None: raise SystemExit(f"Daily film generation failed after 3 attempts: {last}")
    encoded=json.dumps(film,indent=2,ensure_ascii=False)+"\n"
    (LATEST/"film.json").write_text(encoded); (LATEST/"title.txt").write_text(film["title"]+"\n")
    date_dir=ROOT/film["date"]; date_dir.mkdir(exist_ok=True); (date_dir/"film.json").write_text(encoded)
    history.setdefault("used_titles",[]).append(film["title"]); history.setdefault("films",[]).append({"date":film["date"],"title":film["title"],"category":category})
    history["used_titles"]=history["used_titles"][-365:]; history["films"]=history["films"][-365:]
    HISTORY.write_text(json.dumps(history,indent=2,ensure_ascii=False)+"\n")
    print("DAILY TOPIC: "+film["title"]); print("CATEGORY: "+category); print("SCENES: 9; DURATION: 30 seconds")

if __name__=="__main__": main()

#!/usr/bin/env python3
"""Create one connected fictional series part with continuity memory."""
import json, os, re, time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'settings.json').read_text())
KEY=os.environ['GEMINI_API_KEY']; MODEL=os.getenv('GEMINI_MODEL') or CFG['gemini_model']
API=f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
def ask(prompt,temp=.7):
 p={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':temp,'responseMimeType':'application/json'}}
 for n in range(5):
  r=requests.post(API,params={'key':KEY},json=p,timeout=180)
  if r.ok: return json.loads(re.sub(r'^\s*```json\s*|\s*```\s*$','',r.json()['candidates'][0]['content']['parts'][0]['text'].strip()))
  if r.status_code not in (429,500,502,503): r.raise_for_status()
  time.sleep(3*(n+1))
 r.raise_for_status()
def slug(s): return re.sub(r'[^a-z0-9]+','-',s.casefold()).strip('-')[:70] or 'new-series'
title=os.getenv('SERIES_TITLE','').strip(); sid=slug(os.getenv('SERIES_SLUG','') or title)
genre=os.getenv('SERIES_GENRE','zombie outbreak survival thriller')
season=int(os.getenv('SEASON_NUMBER','1')); part=int(os.getenv('PART_NUMBER','1'))
if season<1 or part<1: raise ValueError('Season and part must be positive')
root=ROOT/'series'/sid; bible=root/'series.json'
if bible.exists(): show=json.loads(bible.read_text()); title=show['title']; genre=show['genre']
else:
 if not title: raise ValueError('SERIES_TITLE required for a new series')
 root.mkdir(parents=True,exist_ok=True)
 c=ask(f'Invent an original serialized {genre} show titled {title!r}. Return JSON: logline, premise, world_rules list, characters list (name, role, appearance, personality), long_arc. Do not copy existing franchises.')
 show={'series_id':sid,'title':title,'genre':genre,**c}; bible.write_text(json.dumps(show,indent=2,ensure_ascii=False)+'\n')
out=root/f'season-{season:02d}'/f'part-{part:03d}'
if out.exists(): raise FileExistsError(f'{out} exists; refusing overwrite')
history=[]
for p in sorted(root.glob('season-*/part-*/continuity.json')):
 try: history.append(json.loads(p.read_text()))
 except (OSError,json.JSONDecodeError): pass
plan=ask(f'''Show bible: {json.dumps(show,ensure_ascii=False)}\nPrevious parts: {json.dumps(history[-12:],ensure_ascii=False)}\nWrite Season {season} Part {part} continuing the same story with consistent characters, world rules and consequences. Return JSON: title, description, ending_recap, open_threads, next_part_teaser, scenes. Exactly 48 ordered scenes with scene_number 1..48, narration (20-30 spoken words) and visual_beat. Total narration 1100-1350 words. Strong hook, escalating stakes, character moments and cliffhanger. Fiction, not an explainer.''')
scenes=plan.get('scenes',[])
if len(scenes)!=48 or [s.get('scene_number') for s in scenes]!=list(range(1,49)): raise ValueError('Expected 48 ordered scenes')
visual=ask('Create exactly 48 original cinematic 16:9 image prompts matching these scenes and consistent character appearances. No text, logos, franchise characters or imitation of named studios/artists. Return JSON {"prompts":[{"scene_number":1,"prompt":"..."}]}. BIBLE: '+json.dumps(show,ensure_ascii=False)+' SCENES: '+json.dumps(scenes,ensure_ascii=False),.55)
prompts=visual.get('prompts',[])
if len(prompts)!=48 or [p.get('scene_number') for p in prompts]!=list(range(1,49)): raise ValueError('Expected 48 ordered prompts')
images=out/'images'/'incoming'; images.mkdir(parents=True)
et=str(plan.get('title') or f'Part {part}').strip()
(out/'episode.json').write_text(json.dumps({'series_id':sid,'series_title':title,'season_number':season,'part_number':part,'title':et,'description':plan.get('description',''),'scene_count':48,'target_minutes':'8-10','status':'awaiting_images','content_type':'fictional_serial'},indent=2,ensure_ascii=False)+'\n')
lines=[f'# {et}','','',str(plan.get('description','')),'']
for s in scenes: lines += [f"## Scene {s['scene_number']:02d}",'',str(s['narration']).strip(),'']
(out/'script.md').write_text('\n'.join(lines))
(out/'scenes.json').write_text(json.dumps(scenes,indent=2,ensure_ascii=False)+'\n')
lines=[f'# Visual prompts — {title} S{season:02d} P{part:03d}','']
for p in prompts: lines += [f"## Scene {p['scene_number']:02d}",'',p['prompt'].strip(),'']
(out/'image-prompts.md').write_text('\n'.join(lines))
(out/'continuity.json').write_text(json.dumps({'series_id':sid,'season_number':season,'part_number':part,'title':et,'ending_recap':plan.get('ending_recap',''),'open_threads':plan.get('open_threads',[]),'next_part_teaser':plan.get('next_part_teaser',''),'characters':show.get('characters',[])},indent=2,ensure_ascii=False)+'\n')
(images/'.gitkeep').write_text('')
print(f'Created {sid}/season-{season:02d}/part-{part:03d}: {et}')
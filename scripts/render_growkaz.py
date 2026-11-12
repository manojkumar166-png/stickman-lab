#!/usr/bin/env python3
"""Bridge the existing ScriptForge story JSON and voiceover into GrowKaz Stickman Studio.

The upstream GrowKaz kit is supplied by the user in vendor/GrowKaz_Stickman.plugin.
This adapter creates a deterministic, renderer-compatible project; it does not call image/video AI.
"""
import argparse, json, os, re, shutil, subprocess
from pathlib import Path

def run(cmd, cwd=None):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(list(map(str, cmd)), cwd=cwd, check=True)

def slugify(s):
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:48] or "explainer"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True)
    ap.add_argument("--story", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--out", default="output")
    ap.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"])
    ap.add_argument("--resolution", default="1080p", choices=["720p", "1080p", "1440p", "2160p"])
    ap.add_argument("--style", default="emerald", choices=["emerald", "ember", "arctic", "sakura", "retro"])
    a = ap.parse_args()
    kit, story_path, voice_path = Path(a.kit).resolve(), Path(a.story).resolve(), Path(a.voice).resolve()
    story = json.loads(story_path.read_text(encoding="utf-8"))
    scenes = story.get("scenes") or []
    if not scenes: raise SystemExit("Story JSON contains no scenes.")
    title = str(story.get("topic") or "Animated explainer")
    slug = slugify(title)
    studio = kit
    project = studio / "projects" / slug
    for d in ["input", "timeline", "story", "scenes/sets", "scenes/shots", "build", "out"]:
        (project / d).mkdir(parents=True, exist_ok=True)
    shutil.copy2(voice_path, project / "input" / "voiceover.mp3")
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(voice_path)], check=True, capture_output=True, text=True)
    duration = float(probe.stdout.strip())
    cfg = {"title": title, "aspect": a.aspect, "resolution": a.resolution, "fps": 24, "style": a.style,
           "voiceover": "input/voiceover.mp3", "script": None, "duration": duration, "captions": True,
           "bars": None, "fadeIn": 0.5, "fadeOut": 0.8,
           "music": {"enabled": True, "gainDb": -17}, "sfx": {"enabled": True, "gainDb": -6}, "loudness": -14}
    (project / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    weights = [max(1, len(str(x.get("narration", "")).split())) for x in scenes]
    total = sum(weights)
    cursor, shots, music = 0.0, [], []
    palette = ["#55e0b5", "#ff9b62", "#78b8ff", "#f08ac8", "#e6d36f"]
    for i, scene in enumerate(scenes):
        end = duration if i == len(scenes)-1 else cursor + duration * weights[i] / total
        line = str(scene.get("narration", "")).strip()
        visual = str(scene.get("visual", "")).strip()
        bg = str(scene.get("background", "city")).lower()
        action = str(scene.get("action", "explain")).lower()
        sfx = [{"at": 0.12, "name": "whoosh", "gain": -14}]
        if action in ("surprised", "celebrate", "run"): sfx.append({"at": 0.55, "name": "impact", "gain": -12})
        shots.append({"id": f"s{i+1:03d}", "start": round(cursor, 3), "end": round(end, 3),
                      "line": line, "scene": visual, "set": bg, "bars": None,
                      "in": {"type": "cut" if i == 0 else "dip", "dur": 0.18},
                      "sfx": sfx, "notes": f"GrowKaz procedural scene; action={action}"})
        cursor = end
    music = [{"start": 0, "end": duration, "mood": "wonder", "intensity": 0.55}]
    (project / "story" / "shots.json").write_text(json.dumps({"title": title, "duration": duration, "shots": shots, "music": music}, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "scenes" / "cast.js").write_text(
        "export const HERO = { top: 'hoodie', color: '#55e0b5', head: 'none' };\\n"
        "export const SECOND = { top: 'tshirt', color: '#ff9b62', head: 'none' };\\n"
        "export const CAST = [HERO, SECOND];\\n", encoding="utf-8")
    for i, scene in enumerate(scenes):
        sid = f"s{i+1:03d}"
        desc = json.dumps(str(scene.get("title") or title), ensure_ascii=False)
        visual = json.dumps(str(scene.get("visual") or ""), ensure_ascii=False)
        action = str(scene.get("action", "explain")).lower()
        pose = {"walk":"explain", "run":"ready", "point":"point", "think":"think", "surprised":"handsOnHead", "celebrate":"cheer", "observe":"pointUp"}.get(action, "explain")
        color = palette[i % len(palette)]
        # Each shot is original code-drawn 2D/2.5D animation using the GrowKaz rig, lighting, atmosphere and UI primitives.
        js = f"""import {{ E, V, registerShot, mood, backdrop, ease, prog, text, seg, circle }} from '/engine/core.js';
import {{ drawFigure, POSES, breathe }} from '/engine/rig2d.js';
import * as FX from '/engine/fx2d.js';
import * as UI from '/engine/ui2d.js';
import {{ HERO, SECOND }} from '../cast.js';
registerShot('{sid}', {{ draw(g, t, info) {{
  const M = mood('{["dusk","night","golden","storm","interiorCool"][i % 5]}');
  backdrop(g, M.sky);
  FX.skyline(g, {{ x: -80, y: E.H * V(0.76, 0.64), w: E.W + 160, maxH: V(280, 420), color: '#171b2b', windowColor: M.practical, seed: {i+11} }});
  g.fillStyle = M.floor; g.fillRect(0, E.H * V(0.80, 0.72), E.W, E.H * 0.3);
  for (let k=0;k<12;k++) seg(g, [[k*E.W/10, E.H*V(0.84,0.78)],[k*E.W/10-90,E.H]], 2, 'rgba(255,255,255,.055)');
  const bob = Math.sin(t*2.4)*5;
  drawFigure(g, {{ x: E.W*0.50 + Math.sin(t*0.65)*22, y: E.H*V(0.84,0.78)+bob, s: V(1.55,1.28), facing: 1,
    outfit: HERO, pose: breathe(POSES.{pose}, t), expr: '{action === "surprised" ? "surprised" : action === "think" ? "neutral" : "neutral"}',
    rim: {{ color: M.rim, dir: [-1,-1], w: 5 }} }});
  if ({i} % 4 === 2) drawFigure(g, {{ x: E.W*0.77, y: E.H*V(0.84,0.78), s: V(1.1,0.9), facing: -1, outfit: SECOND, pose: breathe(POSES.point, t, 1, 3), expr: 'neutral', rim: {{ color: '{color}', dir: [1,-1], w: 4 }} }});
  FX.dust(g, t, {{ count: 24, color: M.rim, a: 0.18 }});
  UI.badge(g, {{ str: {desc}, a: ease.out(prog(t,0.15,0.7)), size: V(30,34) }});
  text(g, {visual}, E.W*0.5, E.H*V(0.22,0.18), {{ size: V(34,42), color: '#fff4e8', weight: 700, align: 'center',  }});
}} }});
"""
        (project / "scenes" / "shots" / f"{sid}.js").write_text(js, encoding="utf-8")
    # Preview sheet first, then full render; the workflow uploads both for QC.
    run(["node", "render.mjs", "--project", f"projects/{slug}", "--sheet", "--scale", "0.35", "--workers", "2"], cwd=studio)
    run(["node", "render.mjs", "--project", f"projects/{slug}", "--workers", "2", "--crf", "20"], cwd=studio)
    run(["python", "audio/mix.py", "--project", f"projects/{slug}"], cwd=studio)
    final = project / "out" / ((re.sub(r"[^\\w\\- ]+", "", title).strip().replace(" ", "_") or slug) + ".mp4")
    if not final.exists():
        candidates = list((project / "out").rglob("*.mp4"))
        if not candidates: raise SystemExit("GrowKaz render completed without an MP4 output.")
        final = candidates[0]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, out / "growkaz-stickman-explainer.mp4")
    shutil.copy2(project / "story" / "shots.json", out / "growkaz-shots.json")
    shutil.copy2(project / "build" / "sheets" / "sheet_01.png", out / "growkaz-contact-sheet.png")
    print("GROWKAZ_VIDEO=" + str(out / "growkaz-stickman-explainer.mp4"))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Topic-aware cinematic scene rendering and lightweight procedural sound design."""
import math
import random
import wave
from array import array
from pathlib import Path

TOPIC_RULES = [
    ("space", ("space", "planet", "star", "galaxy", "black hole", "cosmos", "universe", "orbit", "gravity", "moon", "mars", "sun")),
    ("biology", ("cell", "cells", "brain", "neuron", "dna", "blood", "heart", "body", "organ", "bacteria", "virus", "evolution")),
    ("chemistry", ("chemical", "molecule", "atom", "reaction", "element", "electron", "proton", "bond", "acid", "compound")),
    ("technology", ("artificial intelligence", "machine learning", "computer", "robot", "chip", "algorithm", "quantum", "digital", "technology", "neural network")),
    ("earth", ("earth", "ocean", "volcano", "climate", "forest", "mountain", "weather", "dinosaur", "fossil", "ecosystem", "nature")),
]

IMPACT_RULES = {
    "explosion": ("explode", "explosion", "detonate", "collision", "smash", "impact", "crash"),
    "electric": ("electric", "electricity", "lightning", "spark", "charged", "voltage", "current"),
    "reveal": ("discover", "revealed", "uncover", "suddenly", "remarkable", "breakthrough", "impossible"),
    "gravity": ("gravity", "black hole", "collapse", "pulls inward", "warps space"),
    "energy": ("energy burst", "release energy", "ignites", "superheated", "erupts"),
}

PROFILES = {
    "space": {"saturation": 1.16, "contrast": 1.10, "brightness": -0.015},
    "biology": {"saturation": 1.08, "contrast": 1.06, "brightness": 0.005},
    "chemistry": {"saturation": 1.18, "contrast": 1.10, "brightness": 0.0},
    "technology": {"saturation": 1.20, "contrast": 1.12, "brightness": -0.005},
    "earth": {"saturation": 1.12, "contrast": 1.07, "brightness": 0.005},
    "general": {"saturation": 1.06, "contrast": 1.06, "brightness": 0.0},
}

def detect_topic(title, narration):
    text = (str(title) + " " + " ".join(narration)).lower()
    scores = {name: sum(text.count(term) for term in terms) for name, terms in TOPIC_RULES}
    best = max(scores, key=scores.get)
    return best if scores[best] else "general"

def analyze_scenes(title, narration, max_impacts=6):
    topic = detect_topic(title, narration)
    candidates = []
    for index, line in enumerate(narration):
        lowered = line.lower()
        kinds = [kind for kind, terms in IMPACT_RULES.items() if any(term in lowered for term in terms)]
        if kinds:
            candidates.append((index, kinds[0]))
    # Keep impacts distributed through the episode and cap them to avoid visual fatigue.
    if len(candidates) > max_impacts:
        chosen = []
        for slot in range(max_impacts):
            chosen.append(candidates[round(slot * (len(candidates) - 1) / max(1, max_impacts - 1))])
        candidates = list(dict(chosen).items())
        candidates = [(idx, kind) for idx, kind in candidates]
    impact_map = dict(candidates)
    return {
        "topic": topic,
        "profile": PROFILES[topic],
        "scenes": [
            {"impact": impact_map.get(i), "camera": "push_in" if i % 2 == 0 else "drift"}
            for i in range(len(narration))
        ],
    }

def render_scene_clip(image, output, seconds, width, height, fps, profile, scene_plan):
    frames = max(1, round(float(seconds) * int(fps)))
    saturation = profile["saturation"]
    contrast = profile["contrast"]
    brightness = profile["brightness"]
    if scene_plan["camera"] == "push_in":
        camera = "zoompan=z='min(zoom+0.00045,1.055)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={}x{}:fps={}".format(width, height, fps)
    else:
        camera = "zoompan=z='min(zoom+0.00025,1.035)':x='iw/2-(iw/zoom/2)+8*sin(on/55)':y='ih/2-(ih/zoom/2)+5*cos(on/65)':d=1:s={}x{}:fps={}".format(width, height, fps)
    filters = [
        "scale={}:{}:force_original_aspect_ratio=increase".format(width, height),
        "crop={}:{}".format(width, height),
        camera,
        "eq=saturation={:.3f}:contrast={:.3f}:brightness={:.3f}".format(saturation, contrast, brightness),
        "vignette=PI/5",
        "noise=alls=1.2:allf=t",
        "drawbox=x=(120+t*13)%iw:y=(180+t*9)%ih:w=3:h=3:color=white@0.18:t=fill",
        "drawbox=x=(420+t*8)%iw:y=(360+t*12)%ih:w=2:h=2:color=white@0.14:t=fill",
        "drawbox=x=(760+t*11)%iw:y=(120+t*7)%ih:w=3:h=3:color=white@0.16:t=fill",
        "drawbox=x=(980+t*6)%iw:y=(520+t*10)%ih:w=2:h=2:color=white@0.12:t=fill",
    ]
    if scene_plan.get("impact"):
        filters.append("drawbox=x=0:y=0:w=iw:h=ih:color=white@0.22:t=fill:enable='lt(t,0.075)'")
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", str(fps), "-i", str(image),
        "-vf", ",".join(filters), "-frames:v", str(frames), "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", str(output)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _sound_event(kind, rate, duration):
    count = max(1, int(rate * duration))
    values = array("h")
    rng = random.Random(kind + str(count))
    phase = 0.0
    for n in range(count):
        t = n / rate
        fade = min(1.0, t / 0.025, max(0.0, (duration - t) / 0.10))
        noise = rng.uniform(-1.0, 1.0)
        if kind == "impact":
            freq = 95 + 35 * math.exp(-t * 8)
            sample = math.sin(phase) * math.exp(-t * 7) + noise * 0.22 * math.exp(-t * 12)
        else:
            freq = 620 - 420 * (t / duration)
            sample = math.sin(phase) * 0.55 + noise * 0.30
        phase += 2 * math.pi * freq / rate
        values.append(int(max(-1.0, min(1.0, sample * fade * 0.20)) * 32767))
    return values

def create_sound_effect_track(path, duration, scene_durations, scene_plans, sample_rate=22050):
    total = max(1, int(math.ceil(duration * sample_rate)))
    mix = array("h", [0]) * total
    elapsed = 0.0
    events = []
    for index, (seconds, plan) in enumerate(zip(scene_durations, scene_plans)):
        if index and index % 4 == 0:
            events.append((elapsed, "whoosh", 0.42))
        if plan.get("impact"):
            events.append((elapsed + min(0.18, seconds * 0.08), "impact", 0.62))
        elapsed += seconds
    for start, kind, length in events:
        samples = _sound_event(kind, sample_rate, length)
        offset = max(0, int(start * sample_rate))
        for j, value in enumerate(samples):
            pos = offset + j
            if pos >= total:
                break
            mixed = mix[pos] + int(value * 0.55)
            mix[pos] = max(-32768, min(32767, mixed))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(mix.tobytes())

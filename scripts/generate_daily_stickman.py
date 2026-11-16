#!/usr/bin/env python3
"""Generate a fresh 30-second stickman film package without requiring an API key."""

import argparse
import datetime as dt
import json
import pathlib
import random
import re
import sys

BASE = pathlib.Path("stickman-films")
HISTORY = BASE / "history.json"
LATEST = BASE / "latest"
BANNED = {"the door that opens to tomorrow"}

PREMISES = [
    ("The Umbrella That Remembers Rain", "A stickman finds an umbrella that opens only when someone nearby is sad."),
    ("One Second of Time Stop", "He can freeze time for one second each day and uses it to catch a falling cup for a stranger."),
    ("The Last Coin", "He gives his last coin to a stranger, who leaves him a mysterious map."),
    ("The Invisible Friend's Chair", "A second chair moves by itself after he sets it out every morning."),
    ("The Lighthouse Text", "A lonely lighthouse keeper receives a message from a wrong number that becomes a friendship."),
    ("The Elevator That Goes to Yesterday", "An elevator in his building has a button marked Yesterday."),
    ("The Plant That Listens", "His plant leans toward his voice, so he starts telling it the truth."),
    ("The Lost Glove", "He finds the same glove on a bench every winter and finally waits to return it."),
    ("The Paper Plane Message", "A paper plane lands on his balcony with a message telling him not to give up."),
    ("The Clock That Runs Backwards at Night", "At 3 a.m. his clock runs backwards and reveals a moment he missed."),
    ("The Stranger's Smile", "A stranger smiles at him on a train, and he spends the day passing that kindness on."),
    ("The Borrowed Umbrella", "He lends his umbrella to a stranger and later gets it back with a note."),
    ("The Empty Seat", "He saves a seat at dinner for someone he misses, until a child asks him about it."),
    ("The Rooftop Message Bottle", "A bottle on his rooftop contains a wish written ten years earlier."),
    ("The Tiny Door in the Wall", "A tiny door appears in his room and opens only when he helps someone."),
    ("The Bench That Saves a Place", "A park bench is always warm on the coldest mornings."),
    ("The Forgotten Birthday", "He plans a birthday surprise for a neighbour who thinks everyone forgot."),
    ("The Streetlight That Winks", "One streetlight flickers whenever someone nearby needs help."),
    ("The Train Ticket Home", "An unused train ticket leads him to a person waiting for an apology."),
    ("The Snow Globe Summer", "A snow globe shows a sunny memory whenever he feels alone."),
]

def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())

def load_history():
    if not HISTORY.exists():
        return {"used_titles": [], "used_premises": [], "films": []}
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("history must be a JSON object")
        data.setdefault("used_titles", [])
        data.setdefault("used_premises", [])
        data.setdefault("films", [])
        return data
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read {HISTORY}: {exc}")

def existing_titles(history):
    titles = {norm(t) for t in history.get("used_titles", [])}
    for item in history.get("films", []):
        if isinstance(item, dict):
            titles.add(norm(item.get("title")))
    if BASE.exists():
        for path in BASE.rglob("film.json"):
            if path == LATEST / "film.json":
                continue
            try:
                film = json.loads(path.read_text(encoding="utf-8"))
                titles.add(norm(film.get("title")))
            except (OSError, json.JSONDecodeError, AttributeError):
                print(f"Warning: skipped unreadable film file: {path}", file=sys.stderr)
    titles.discard("")
    return titles

def pick_fresh(history, requested=""):
    used = existing_titles(history) | BANNED
    if requested:
        title = requested.strip()
        if norm(title) not in used:
            return title, f"A stickman story about: {title}"
        print(f"Requested topic is already used or banned: {title}. Choosing a fresh topic.")

    candidates = PREMISES[:]
    random.SystemRandom().shuffle(candidates)
    for title, premise in candidates:
        if norm(title) not in used:
            return title, premise

    adjectives = ["Quiet", "Little", "Golden", "Brave", "Lost", "Gentle", "Hidden", "Silver",
                  "Curious", "Patient", "Midnight", "Paper", "Pocket", "Distant", "Kind"]
    nouns = ["Letter", "Key", "Window", "Train", "Star", "Song", "Bridge", "Lantern",
             "Footprint", "Postcard", "Kite", "時計", "Pebble", "Promise", "Comet"]
    for _ in range(1000):
        title = f"The {random.choice(adjectives)} {random.choice(nouns)}"
        if norm(title) not in used:
            return title, f"A stickman discovers {title.lower()}, changing one ordinary day."
    raise SystemExit("Could not find a unique title; expand the title generator.")

def build_film(title, premise, style):
    today = dt.date.today().isoformat()
    scenes = [
        {"n": 1, "title": "Alone", "start": 0, "end": 3, "camera": "Wide, slow push-in", "sound": "Quiet room ambience", "action": "The friendly hero is alone, looking at an everyday object."},
        {"n": 2, "title": "Something strange", "start": 3, "end": 5, "camera": "Medium shot", "sound": "Soft magical rumble", "action": "A mysterious event connected to the premise appears."},
        {"n": 3, "title": "Curiosity", "start": 5, "end": 8, "camera": "Side tracking", "sound": "Gentle footsteps", "action": "The hero approaches carefully and reaches out."},
        {"n": 4, "title": "Discovery", "start": 8, "end": 11, "camera": "Close-up", "sound": "Click and soft chime", "action": "The hero interacts with the object and discovers its secret."},
        {"n": 5, "title": "The glimpse", "start": 11, "end": 14, "camera": "Over-the-shoulder", "sound": "Airy transition", "action": "A revealing image or memory appears."},
        {"n": 6, "title": "The truth", "start": 14, "end": 18, "camera": "Slow push-in", "sound": "Soft heartbeat", "action": "The emotional meaning of the discovery becomes clear."},
        {"n": 7, "title": "The choice", "start": 18, "end": 22, "camera": "Close-up reaction", "sound": "Gentle musical sting", "action": "The hero decides to do something kind."},
        {"n": 8, "title": "A small action", "start": 22, "end": 27, "camera": "Medium shot", "sound": "Message sent tone", "action": "The hero acts: helps someone, returns something, or reaches out."},
        {"n": 9, "title": "A different tomorrow", "start": 27, "end": 30, "camera": "Slow pull-back", "sound": "Warm chime", "action": "A hopeful final moment shows the small change mattered."},
    ]
    return {
        "title": title, "premise": premise, "date": today,
        "style": style, "length": "30 seconds", "total_seconds": 30,
        "voiceover": False, "background_music": False, "sound_effects": True,
        "hero": "Friendly 2D stickman; cream round face, warm brown eyes with highlights, gentle smile, coral hoodie with darker red hood, dark trousers; never scary.",
        "end_card": "One small kindness can change everything.",
        "scenes": scenes,
        "youtube": {
            "titles": [f"{title} | A Stickman Short Film",
                       f"He Found {title}... And Everything Changed",
                       "This 30-Second Stickman Film Will Make You Smile"],
            "thumbnail_text": title.upper()[:18]
        }
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-topic", default="")
    parser.add_argument("--style", default="2D cinematic")
    args = parser.parse_args()

    BASE.mkdir(parents=True, exist_ok=True)
    history = load_history()
    title, premise = pick_fresh(history, args.force_topic)
    film = build_film(title, premise, args.style)
    date_folder = BASE / dt.date.today().isoformat()
    LATEST.mkdir(parents=True, exist_ok=True)
    date_folder.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(film, indent=2, ensure_ascii=False) + "\n"
    (LATEST / "film.json").write_text(payload, encoding="utf-8")
    (LATEST / "title.txt").write_text(title + "\n", encoding="utf-8")
    (date_folder / "film.json").write_text(payload, encoding="utf-8")

    history["used_titles"].append(title)
    history["used_premises"].append(premise)
    history["films"].append({"date": film["date"], "title": title})
    HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FRESH TOPIC: {title}")

if __name__ == "__main__":
    main()

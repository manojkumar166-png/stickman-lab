#!/usr/bin/env python3
"""Poll Telegram for episode images and stage them in the selected episode folder."""
import json
import os
import re
from pathlib import Path
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
STATE_PATH = Path("science-channel/telegram-bot-state.json")
ROOT = Path("science-channel/daily-episodes")
SCENE_RE = re.compile(r"(?:scene[-_ ]?)?(0?[1-9]|[1-4][0-9])\b", re.I)
EPISODE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[/ ](episode-\d{3})$")

def api(method, **kwargs):
    response = requests.post(f"{API}/{method}", timeout=60, **kwargs)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]

def send(text):
    api("sendMessage", data={"chat_id": CHAT_ID, "text": text})

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"offset": 0, "episode_path": ""}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

def valid_episode(value):
    match = EPISODE_RE.fullmatch(value.strip())
    if not match:
        return None
    path = ROOT / match.group(1) / match.group(2)
    if not (path / "episode.json").is_file():
        return None
    return path

def image_payload(message):
    if message.get("photo"):
        photo = message["photo"][-1]
        return photo["file_id"], "jpg"
    doc = message.get("document") or {}
    mime = doc.get("mime_type", "")
    if mime.startswith("image/"):
        ext = (doc.get("file_name", "").rsplit(".", 1)[-1] or mime.split("/")[-1]).lower()
        if ext == "jpeg":
            ext = "jpg"
        if ext in {"jpg", "png", "webp"}:
            return doc["file_id"], ext
    return None, None

def main():
    state = load_state()
    updates = api("getUpdates", params={"offset": state.get("offset", 0), "timeout": 0, "allowed_updates": json.dumps(["message"])})
    changed = False
    for update in updates:
        state["offset"] = update["update_id"] + 1
        msg = update.get("message", {})
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != CHAT_ID:
            continue
        text = (msg.get("text") or "").strip()
        if text.startswith("/start") or text.startswith("/help"):
            send("Send /episode YYYY-MM-DD/episode-001 to select an episode. Then send up to 48 images. Caption an image scene-01 through scene-48, or I’ll assign the next missing scene. I create READY.txt only when all 48 are present.")
            continue
        if text.startswith("/episode"):
            value = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""
            folder = valid_episode(value)
            if not folder:
                send("I couldn't find that episode. Use /episode YYYY-MM-DD/episode-001 and make sure the episode already exists in the repository.")
            else:
                state["episode_path"] = str(folder)
                changed = True
                send(f"Selected {folder.parent.name}/{folder.name}. Send images with captions scene-01 to scene-48, or send them without captions for automatic numbering.")
            continue
        file_id, ext = image_payload(msg)
        if not file_id:
            continue
        episode = Path(state.get("episode_path", ""))
        if not state.get("episode_path") or not (episode / "episode.json").is_file():
            send("Select an episode first using /episode YYYY-MM-DD/episode-001.")
            continue
        caption = (msg.get("caption") or "").strip()
        match = SCENE_RE.search(caption)
        if match:
            number = int(match.group(1))
        else:
            present = {int(m.group(1)) for p in (episode / "images/incoming").glob("scene-*.*") if (m := re.match(r"scene-(\d{2})\.", p.name))}
            number = next((n for n in range(1, 49) if n not in present), 0)
        if not 1 <= number <= 48:
            send("All 48 scene slots are already filled. No more images were added.")
            continue
        dest_dir = episode / "images/incoming"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"scene-{number:02d}.{ext}"
        if dest.exists():
            send(f"Scene {number:02d} already has an image. I left it unchanged; rename or remove the existing file before replacing it.")
            continue
        info = api("getFile", data={"file_id": file_id})
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}"
        download = requests.get(file_url, timeout=120)
        download.raise_for_status()
        if len(download.content) > 20 * 1024 * 1024:
            send("That image is over 20 MB, so it was skipped. Please send a smaller image.")
            continue
        dest.write_bytes(download.content)
        changed = True
        present = {int(m.group(1)) for p in dest_dir.glob("scene-*.*") if (m := re.match(r"scene-(\d{2})\.", p.name))}
        missing = [n for n in range(1, 49) if n not in present]
        if not missing:
            ready = episode / "READY.txt"
            ready.write_text("All 48 scene images received through Telegram.\n", encoding="utf-8")
            send(f"All 48 images are present for {episode.parent.name}/{episode.name}. READY.txt created; video rendering will start after this upload is committed.")
        else:
            send(f"Saved scene {number:02d}. {len(present)}/48 images received. Next missing: scene-{missing[0]:02d}.")
    if changed or state.get("offset"):
        save_state(state)

if __name__ == "__main__":
    main()

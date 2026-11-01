#!/usr/bin/env python3
"""Poll Telegram for episode images and stage them in the selected episode folder."""
import json
import os
import re
import io
import zipfile
from pathlib import Path
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
STATE_PATH = Path("science-channel/telegram-bot-state.json")
ROOT = Path("science-channel/daily-episodes")
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

def newest_episode():
    episodes = []
    if ROOT.exists():
        for date_dir in ROOT.iterdir():
            if not date_dir.is_dir() or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_dir.name):
                continue
            for episode_dir in date_dir.glob("episode-*"):
                if episode_dir.is_dir() and (episode_dir / "episode.json").is_file():
                    episodes.append(episode_dir)
    return max(episodes, key=lambda p: (p.parent.name, p.name)) if episodes else None

def image_payload(message):
    if message.get("photo"):
        photo = message["photo"][-1]
        return photo["file_id"], "jpg"
    doc = message.get("document") or {}
    mime = doc.get("mime_type", "")
    filename = doc.get("file_name", "").lower()
    if filename.endswith(".zip") or mime in {"application/zip", "application/x-zip-compressed"}:
        return doc["file_id"], "zip"
    if mime.startswith("image/"):
        ext = (filename.rsplit(".", 1)[-1] or mime.split("/")[-1]).lower()
        if ext == "jpeg":
            ext = "jpg"
        if ext in {"jpg", "png", "webp"}:
            return doc["file_id"], ext
    return None, None

def scene_numbers(directory):
    found = set()
    if directory.exists():
        for path in directory.glob("scene-*.*"):
            match = re.fullmatch(r"scene-(\d{2})\.(?:jpg|png|webp)", path.name, re.I)
            if match:
                number = int(match.group(1))
                if 1 <= number <= 48:
                    found.add(number)
    return found

def main():
    state = load_state()
    latest = newest_episode()
    selected = valid_episode(state.get("episode_path", "")) if state.get("episode_path") else None
    if latest and (selected is None or (latest.parent.name, latest.name) > (selected.parent.name, selected.name)):
        state["episode_path"] = str(latest)
        send(f"Automatically selected newest episode: {latest.parent.name}/{latest.name}. Send 48 images in order, or one ZIP containing exactly 48 images.")

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
            send("I automatically select the newest episode. Send 48 images one by one, or one ZIP containing exactly 48 images. You can use /episode YYYY-MM-DD/episode-001 to choose another existing episode. I create READY.txt only after all 48 images are present.")
            continue
        if text.startswith("/episode"):
            value = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""
            folder = valid_episode(value)
            if not folder:
                send("Episode not found on the adaptive-cinematic-effects branch. Use /episode YYYY-MM-DD/episode-001 and make sure the package has been committed first.")
            else:
                state["episode_path"] = str(folder)
                changed = True
                send(f"Selected {folder.parent.name}/{folder.name}. Send images in order.")
            continue

        file_id, ext = image_payload(msg)
        if not file_id:
            continue
        episode = Path(state.get("episode_path", ""))
        if not state.get("episode_path") or not (episode / "episode.json").is_file():
            send("No committed episode is selected yet. Wait for the planner to publish the package, then send the images again.")
            continue

        dest_dir = episode / "images/incoming"
        dest_dir.mkdir(parents=True, exist_ok=True)
        present = scene_numbers(dest_dir)

        info = api("getFile", data={"file_id": file_id})
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}"
        download = requests.get(file_url, timeout=120)
        download.raise_for_status()
        if len(download.content) > 50 * 1024 * 1024:
            send("Upload is over 50 MB and was skipped. Please send a smaller file.")
            continue

        if ext == "zip":
            try:
                with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                    entries = [item for item in archive.infolist()
                               if not item.is_dir() and item.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
                    entries.sort(key=lambda item: item.filename.lower())
                    if len(entries) != 48:
                        send(f"ZIP skipped: found {len(entries)} supported images; it must contain exactly 48.")
                        continue
                    images = [(archive.read(item), item.filename) for item in entries]
            except (zipfile.BadZipFile, RuntimeError, OSError):
                send("I couldn't read that ZIP. Please send a valid ZIP containing exactly 48 images.")
                continue
            if present:
                send("ZIP skipped because this episode already has images. Send a ZIP only to an empty incoming folder.")
                continue
            if any(len(data) > 20 * 1024 * 1024 for data, _ in images):
                send("ZIP skipped: at least one image is over 20 MB. Please reduce image sizes.")
                continue
            for index, (data, filename) in enumerate(images, start=1):
                suffix = Path(filename).suffix.lower().lstrip(".")
                suffix = "jpg" if suffix == "jpeg" else suffix
                (dest_dir / f"scene-{index:02d}.{suffix}").write_bytes(data)
            changed = True
        else:
            if len(download.content) > 20 * 1024 * 1024:
                send("Image is over 20 MB and was skipped. Please reduce its size.")
                continue
            if len(present) >= 48:
                send("All 48 scene slots are already filled. No more images were added.")
                continue
            number = next((n for n in range(1, 49) if n not in present), 0)
            dest = dest_dir / f"scene-{number:02d}.{ext}"
            dest.write_bytes(download.content)
            changed = True

        present = scene_numbers(dest_dir)
        missing = [n for n in range(1, 49) if n not in present]
        if not missing:
            (episode / "READY.txt").write_text("All 48 scene images received through Telegram.\n", encoding="utf-8")
            send(f"All 48 images are present for {episode.parent.name}/{episode.name}. READY.txt created; the receiver will commit them to GitHub.")
        else:
            send(f"Saved image. {len(present)}/48 received. Next missing: scene-{missing[0]:02d}.")

    if changed or updates:
        save_state(state)

if __name__ == "__main__":
    main()

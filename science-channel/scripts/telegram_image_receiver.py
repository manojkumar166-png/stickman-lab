#!/usr/bin/env python3
"""Process queued Telegram image updates forwarded by the Cloudflare Worker webhook."""
import json
import os
import re
import io
import zipfile
import time
from pathlib import Path
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
STATE_PATH = Path("science-channel/telegram-bot-state.json")
ROOT = Path("science-channel/daily-episodes")
EPISODE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[/ ](episode-\d{3})$")

def api(method, **kwargs):
    """Call Telegram with bounded retries for transient failures."""
    last_error = None
    for attempt in range(1, 5):
        try:
            response = requests.post(f"{API}/{method}", timeout=(15, 60), **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 4:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = max(1, min(60, int(float(retry_after)))) if retry_after else min(30, 2 ** attempt)
                    except ValueError:
                        delay = min(30, 2 ** attempt)
                    print(f"Telegram {method} returned HTTP {response.status_code}; retry {attempt}/4 in {delay}s.", flush=True)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                description = str(data.get("description", data))
                if method == "getUpdates" and "conflict" in description.casefold():
                    raise RuntimeError(
                        "Telegram getUpdates returned 409 Conflict. Another long-polling "
                        "process may be using this bot token. Telegram detail: " + description
                    )
                raise RuntimeError(f"Telegram {method} failed: {description}")
            return data["result"]
        except requests.HTTPError as exc:
            response = exc.response
            try:
                details = response.json().get("description", response.text[:500])
            except (ValueError, AttributeError):
                details = response.text[:500] if response is not None else str(exc)
            if response is not None and response.status_code == 409 and method == "getUpdates":
                raise RuntimeError(
                    "Telegram getUpdates returned 409 Conflict. Another long-polling "
                    "process may be using this bot token. Telegram detail: " + str(details)
                ) from exc
            raise RuntimeError(f"Telegram {method} HTTP error: {details}") from exc
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 4:
                break
            delay = min(30, 2 ** attempt)
            print(f"Telegram {method} network error on attempt {attempt}/4: {exc}; retrying in {delay}s.", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"Telegram {method} failed after 4 attempts: {last_error}") from last_error


def download_file(url):
    """Download Telegram media with retries for temporary network/server errors."""
    last_error = None
    for attempt in range(1, 5):
        try:
            response = requests.get(url, timeout=(20, 120), stream=True)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 4:
                    try:
                        delay = max(1, min(60, int(float(response.headers.get("Retry-After", 2 ** attempt)))))
                    except ValueError:
                        delay = min(30, 2 ** attempt)
                    response.close()
                    print(f"Telegram media download returned HTTP {response.status_code}; retrying in {delay}s.", flush=True)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            content = response.content
            response.close()
            return content
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 4:
                break
            delay = min(30, 2 ** attempt)
            print(f"Telegram media download attempt {attempt}/4 failed: {exc}; retrying in {delay}s.", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"Telegram media download failed after 4 attempts: {last_error}") from last_error

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
            if match and 1 <= int(match.group(1)) <= 48:
                found.add(int(match.group(1)))
    return found

def natural_key(value):
    """Natural-sort filename chunks so scene-2 sorts before scene-10."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", value)]


def order_image_entries(entries):
    """Sort by numeric chunks in each filename; ZIP archive order is never used."""
    return list(enumerate(
        sorted(entries, key=lambda item: (
            natural_key(Path(item.filename).name),
            Path(item.filename).name.casefold(),
            item.filename.casefold(),
        )),
        start=1,
    ))


def main():
    inbox = Path(".github/telegram-inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    update_files = sorted(
        inbox.glob("*.json"),
        key=lambda path: int(path.stem) if path.stem.isdigit() else path.stem,
    )
    if not update_files:
        print("No queued Telegram webhook updates; nothing to process.")
        return

    updates = [json.loads(path.read_text(encoding="utf-8")) for path in update_files]
    state = load_state()
    state_changed = False
    latest = newest_episode()
    selected = valid_episode(state.get("episode_path", "")) if state.get("episode_path") else None
    if latest and (selected is None or (latest.parent.name, latest.name) > (selected.parent.name, selected.name)):
        state["episode_path"] = str(latest)
        state_changed = True
        send(f"Automatically selected newest MAIN-branch episode: {latest.parent.name}/{latest.name}. Send 48 images in order or one ZIP containing exactly 48 images. ZIPs are automatically sorted by scene number when filenames identify scenes; otherwise filenames are natural-sorted.")

    # Telegram updates are durably queued by the Cloudflare Worker as JSON
    # files. Never call deleteWebhook or getUpdates here: the Worker owns delivery.
    changed = state_changed
    for update in updates:
        state["offset"] = update["update_id"] + 1
        msg = update.get("message", {})
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != CHAT_ID:
            continue
        text = (msg.get("text") or "").strip()
        if text.startswith("/start") or text.startswith("/help"):
            send("This bot only handles episodes committed on the main branch. Send 48 images one by one or one ZIP containing exactly 48 images. Use /episode YYYY-MM-DD/episode-001 to select another existing main-branch episode.")
            continue
        if text.startswith("/episode"):
            value = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""
            folder = valid_episode(value)
            if not folder:
                send("Episode not found on main. Use /episode YYYY-MM-DD/episode-001 and ensure the episode package exists on the main branch.")
            else:
                state["episode_path"] = str(folder)
                changed = True
                send(f"Selected main-branch episode {folder.parent.name}/{folder.name}. Send images in order.")
            continue

        file_id, ext = image_payload(msg)
        if not file_id:
            continue
        episode = Path(state.get("episode_path", ""))
        if not state.get("episode_path") or not (episode / "episode.json").is_file():
            send("No episode committed on main is selected. Wait until the planner publishes one to main, then send your images.")
            continue

        dest_dir = episode / "images/incoming"
        dest_dir.mkdir(parents=True, exist_ok=True)
        present = scene_numbers(dest_dir)
        info = api("getFile", data={"file_id": file_id})
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{info['file_path']}"
        download_content = download_file(file_url)
        if len(download_content) > 50 * 1024 * 1024:
            send("Upload is over 50 MB and was skipped. Please send a smaller file.")
            continue

        if ext == "zip":
            try:
                with zipfile.ZipFile(io.BytesIO(download_content)) as archive:
                    entries = [item for item in archive.infolist()
                               if not item.is_dir() and item.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
                    if len(entries) != 48:
                        send(f"ZIP skipped: found {len(entries)} supported images; it must contain exactly 48.")
                        continue
                    ordered = order_image_entries(entries)
                    images = [(slot, archive.read(item), item.filename) for slot, item in ordered]
            except (zipfile.BadZipFile, RuntimeError, OSError):
                send("I couldn't read that ZIP. Please send a valid ZIP containing exactly 48 images.")
                continue
            if present:
                send("ZIP skipped because this episode already has images. Send a ZIP only to an empty incoming folder.")
                continue
            if any(len(data) > 20 * 1024 * 1024 for _, data, _ in images):
                send("ZIP skipped: at least one image is over 20 MB. Please reduce image sizes.")
                continue
            for index, data, filename in images:
                suffix = Path(filename).suffix.lower().lstrip(".")
                suffix = "jpg" if suffix == "jpeg" else suffix
                (dest_dir / f"scene-{index:02d}.{suffix}").write_bytes(data)
            changed = True
        else:
            if len(download_content) > 20 * 1024 * 1024:
                send("Image is over 20 MB and was skipped. Please reduce its size.")
                continue
            if len(present) >= 48:
                send("All 48 scene slots are already filled. No more images were added.")
                continue
            number = next((n for n in range(1, 49) if n not in present), 0)
            (dest_dir / f"scene-{number:02d}.{ext}").write_bytes(download_content)
            changed = True

        present = scene_numbers(dest_dir)
        missing = [n for n in range(1, 49) if n not in present]
        if not missing:
            (episode / "READY.txt").write_text("All 48 scene images received through Telegram.\n", encoding="utf-8")
            send(f"All 48 images are present for {episode.parent.name}/{episode.name}. ZIP order was normalized automatically using scene numbers when available, otherwise natural filename order. READY.txt created; uploads will be committed to main.")
        else:
            send(f"Saved image. {len(present)}/48 received. Next missing: scene-{missing[0]:02d}.")

    if changed or updates:
        save_state(state)

if __name__ == "__main__":
    main()

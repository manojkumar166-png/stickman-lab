#!/usr/bin/env python3
"""Process queued Telegram image updates forwarded by the Cloudflare Worker webhook."""
import json
import os
import re
import io
import zipfile
import time
import tempfile
from pathlib import Path
import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = str(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"
STATE_PATH = Path("science-channel/telegram-bot-state.json")
ROOT = Path("science-channel/daily-episodes")
EPISODE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[/ ](episode-\d{3}(?:-[A-Za-z0-9][A-Za-z0-9._-]*)?)$")

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
    value = str(value or "").strip()
    prefix = "science-channel/daily-episodes/"
    if value.startswith(prefix):
        value = value[len(prefix):]
    match = EPISODE_RE.fullmatch(value)
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
        key=lambda path: (0, int(path.stem)) if path.stem.isdigit() else (1, path.stem),
    )
    if not update_files:
        print("No queued Telegram webhook updates; nothing to process.")
        return

    updates = [json.loads(path.read_text(encoding="utf-8")) for path in update_files]
    state = load_state()
    state_changed = False
    latest = newest_episode()
    selected = valid_episode(state.get("episode_path", "")) if state.get("episode_path") else None
    manually_selected = bool(state.get("episode_locked", False))
    if latest and (
        selected is None
        or (
            not manually_selected
            and (latest.parent.name, latest.name) > (selected.parent.name, selected.name)
        )
    ):
        state["episode_path"] = str(latest)
        state_changed = True
        send(f"Automatically selected newest MAIN-branch episode: {latest.parent.name}/{latest.name}. Send 48 images in order or one ZIP containing exactly 48 images. ZIPs are automatically sorted by scene number when filenames identify scenes; otherwise filenames are natural-sorted.")

    # Telegram updates are durably queued by the Cloudflare Worker as JSON
    # files. Never call deleteWebhook or getUpdates here: the Worker owns delivery.
    changed = state_changed
    completed_episodes = []
    processed_ids = {
        int(value) for value in state.get("processed_update_ids", [])
        if str(value).isdigit()
    }
    for update in updates:
        update_id = int(update["update_id"])
        if update_id in processed_ids:
            print(f"Skipping already-processed Telegram update {update_id}.", flush=True)
            continue
        state["offset"] = max(int(state.get("offset", 0)), update_id + 1)
        processed_ids.add(update_id)
        msg = update.get("message", {})
        chat = str((msg.get("chat") or {}).get("id", ""))
        if chat != CHAT_ID:
            continue
        text = (msg.get("text") or "").strip()
        if text.startswith("/start") or text.startswith("/help"):
            send("This bot only handles episodes committed on the main branch. Send 48 images one by one or one ZIP containing exactly 48 images. Use /episode YYYY-MM-DD/episode-001-topic-slug to select another existing main-branch episode.")
            continue
        if text.startswith("/episode"):
            value = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""
            folder = valid_episode(value)
            if not folder:
                send("Episode not found on main. Use the exact /episode YYYY-MM-DD/episode-001-topic-slug folder name and ensure the episode package exists on the main branch.")
            else:
                state["episode_path"] = str(folder)
                state["episode_locked"] = True
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
            if present or any(
                item.is_file() and item.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
                for item in dest_dir.iterdir()
            ):
                send("ZIP skipped because this episode already has images. Send a ZIP only to an empty incoming folder.")
                continue
            if len(download_content) > 50 * 1024 * 1024:
                send("ZIP skipped: the archive is over 50 MB.")
                continue
            installed = []
            try:
                with zipfile.ZipFile(io.BytesIO(download_content)) as archive:
                    entries = []
                    total_uncompressed = 0
                    seen_names = set()
                    for item in archive.infolist():
                        if item.is_dir():
                            continue
                        member = Path(item.filename.replace("\\", "/"))
                        mode = (item.external_attr >> 16) & 0o170000
                        if member.is_absolute() or ".." in member.parts or mode == 0o120000:
                            raise ValueError("unsafe archive path or symbolic link")
                        if member.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                            continue
                        if item.file_size <= 0 or item.file_size > 20 * 1024 * 1024:
                            raise ValueError(f"image has invalid or excessive size: {member.name}")
                        total_uncompressed += item.file_size
                        if total_uncompressed > 250 * 1024 * 1024:
                            raise ValueError("archive expands beyond 250 MiB")
                        flat_name = member.name.casefold()
                        if flat_name in seen_names:
                            raise ValueError(f"duplicate image filename: {member.name}")
                        seen_names.add(flat_name)
                        entries.append(item)
                    if len(entries) != 48:
                        send(f"ZIP skipped: found {len(entries)} supported images; it must contain exactly 48.")
                        continue

                    # Stage every extracted image before touching the episode.
                    # A CRC/decompression failure must not leave partial scene files.
                    with tempfile.TemporaryDirectory(prefix=".telegram-zip-", dir=dest_dir) as temp_name:
                        temp_dir = Path(temp_name)
                        staged = []
                        for index, item in order_image_entries(entries):
                            suffix = Path(item.filename).suffix.lower()
                            suffix = ".jpg" if suffix == ".jpeg" else suffix
                            target = temp_dir / f"scene-{index:02d}{suffix}"
                            written = 0
                            with archive.open(item) as source, target.open("wb") as destination:
                                while True:
                                    chunk = source.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    written += len(chunk)
                                    if written > 20 * 1024 * 1024 or written > item.file_size:
                                        raise ValueError(f"image expanded beyond its declared size: {item.filename}")
                                    destination.write(chunk)
                            if written != item.file_size:
                                raise ValueError(f"image size mismatch: {item.filename}")
                            staged.append((target, dest_dir / target.name))
                        archive_copy = temp_dir / "source-upload.zip"
                        archive_copy.write_bytes(download_content)
                        staged.append((archive_copy, dest_dir / "source-upload.zip"))
                        for source, destination in staged:
                            source.replace(destination)
                            installed.append(destination)
            except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, ValueError) as exc:
                # A failed multi-file rename must roll back every file already
                # installed; otherwise a retried ZIP would be rejected as partial.
                for installed_path in installed:
                    installed_path.unlink(missing_ok=True)
                send(f"ZIP skipped: {exc}. Please send a valid ZIP containing exactly 48 supported images.")
                continue
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
            episode_path = str(episode)
            if episode_path not in completed_episodes:
                completed_episodes.append(episode_path)
            if str(state.get("episode_path", "")) == episode_path:
                state["episode_locked"] = False
            send(f"All 48 images are present for {episode.parent.name}/{episode.name}. ZIP order was normalized automatically using scene numbers when available, otherwise natural filename order. READY.txt created; uploads will be committed to main.")
        else:
            send(f"Saved image. {len(present)}/48 received. Next missing: scene-{missing[0]:02d}.")

    if changed or updates:
        # Keep a bounded idempotency window so webhook retries after inbox
        # deletion cannot add the same media to a later scene slot.
        state["processed_update_ids"] = sorted(processed_ids)[-1000:]
        save_state(state)

    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path and completed_episodes:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write("completed_episodes<<EPISODES_EOF\n")
            output.write("\n".join(completed_episodes) + "\n")
            output.write("EPISODES_EOF\n")

    # The inbox files are the durable delivery queue. Remove them only after
    # every queued update has been handled and the receiver state is saved;
    # the workflow commits these deletions together with the imported images.
    for update_file in update_files:
        update_file.unlink(missing_ok=True)

if __name__ == "__main__":
    main()

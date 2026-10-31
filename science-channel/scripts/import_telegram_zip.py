#!/usr/bin/env python3
"""Download a Telegram ZIP, validate its 48 images, and stage them for rendering."""
import os
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath

import requests

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
FILE_ID = os.environ["TELEGRAM_FILE_ID"]
EPISODE_PATH = os.environ["EPISODE_PATH"].strip()
ROOT = Path("science-channel/daily-episodes")
ALLOWED = {".png", ".jpg", ".jpeg", ".webp"}
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024

def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)

def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\\d+)", value)]

def main():
    match = re.fullmatch(
        r"science-channel/daily-episodes/(\\d{4}-\\d{2}-\\d{2})/([A-Za-z0-9][A-Za-z0-9._-]*)",
        EPISODE_PATH,
    )
    if not match or ".." in Path(EPISODE_PATH).parts:
        fail("Invalid episode_path. Expected a folder under science-channel/daily-episodes/YYYY-MM-DD/.")

    episode = Path(EPISODE_PATH)
    if not (episode / "episode.json").is_file():
        fail(f"Episode metadata not found: {EPISODE_PATH}/episode.json")

    api = f"https://api.telegram.org/bot{TOKEN}"
    response = requests.post(f"{api}/getFile", data={"file_id": FILE_ID}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        fail("Telegram could not locate the uploaded ZIP.")
    file_path = payload["result"]["file_path"]
    file_size = int(payload["result"].get("file_size", 0))
    if file_size and file_size > MAX_ZIP_BYTES:
        fail("ZIP exceeds Telegram's 20 MB download limit.")

    download = requests.get(
        f"https://api.telegram.org/file/bot{TOKEN}/{file_path}", timeout=120
    )
    download.raise_for_status()
    if len(download.content) > MAX_ZIP_BYTES:
        fail("ZIP exceeds Telegram's 20 MB download limit.")

    incoming = episode / "images" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    existing = [p for p in incoming.iterdir()
                if p.is_file() and p.suffix.lower() in ALLOWED]
    if existing:
        fail("This episode already contains incoming images. Refusing to overwrite them.")

    try:
        with zipfile.ZipFile(BytesIO(download.content)) as archive:
            image_entries = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                member = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if member.is_absolute() or ".." in member.parts or mode == 0o120000:
                    fail("ZIP contains an unsafe path or symbolic link.")
                if Path(member.name).suffix.lower() in ALLOWED:
                    if info.file_size > MAX_IMAGE_BYTES:
                        fail(f"Image exceeds 20 MB: {member.name}")
                    image_entries.append(info)
            image_entries.sort(key=lambda item: natural_key(item.filename))
            if len(image_entries) != 48:
                fail(f"ZIP must contain exactly 48 supported images; found {len(image_entries)}.")
            names = [Path(item.filename).name.casefold() for item in image_entries]
            if len(set(names)) != 48:
                fail("ZIP contains duplicate image filenames.")
            for index, info in enumerate(image_entries, start=1):
                suffix = Path(info.filename).suffix.lower()
                target = incoming / f"scene-{index:02d}{suffix}"
                target.write_bytes(archive.read(info))
    except zipfile.BadZipFile:
        fail("The uploaded document is not a valid ZIP archive.")

    (episode / "READY.txt").write_text(
        "All 48 scene images imported from Telegram.\\n", encoding="utf-8"
    )
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
        handle.write(f"episode_path={EPISODE_PATH}\\n")
    print(f"Imported 48 images into {incoming}")

if __name__ == "__main__":
    main()

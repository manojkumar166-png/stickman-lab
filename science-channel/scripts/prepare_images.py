#!/usr/bin/env python3
"""Prepare 48 generated science-scene images as a compact, numbered ZIP."""
import argparse
import re
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
SCENE_RE = re.compile(r"(?:scene|img|image)[-_ ]*(\d{1,3})(?!.*\d)", re.I)


def scene_number(path):
    match = SCENE_RE.search(path.stem)
    if match:
        return int(match.group(1))
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[-1]) if numbers else None


def natural_key(path):
    return [(0, int(part)) if part.isdigit() else (1, part.casefold())
            for part in re.split(r"(\d+)", path.name)]


def main():
    parser = argparse.ArgumentParser(
        description="Resize and compress 48 scene images into one GitHub-upload-friendly ZIP."
    )
    parser.add_argument("input_folder", type=Path, help="Folder containing the 48 original images")
    parser.add_argument("output_zip", type=Path, help="Destination ZIP file")
    parser.add_argument("--max-mb", type=float, default=23.0,
                        help="Target ZIP size in MiB (default: 23, below GitHub's 25 MB web limit)")
    args = parser.parse_args()

    files = sorted((p for p in args.input_folder.iterdir()
                    if p.is_file() and p.suffix.lower() in SUPPORTED), key=lambda p: p.name.casefold())
    if len(files) != 48:
        raise SystemExit(f"Expected exactly 48 supported images in {args.input_folder}; found {len(files)}.")

    nums = [scene_number(p) for p in files]
    if all(n is not None for n in nums) and sorted(nums) == list(range(1, 49)):
        files = [p for _, p in sorted(zip(nums, files), key=lambda pair: pair[0])]
    else:
        files = sorted(files, key=natural_key)
        print("Note: filenames do not contain a complete 1–48 scene sequence; using natural filename order.")

    args.output_zip.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(args.max_mb * 1024 * 1024)

    with tempfile.TemporaryDirectory(prefix="science-channel-images-") as temp:
        temp_dir = Path(temp)
        compressed = []
        for index, source in enumerate(files, 1):
            target = temp_dir / f"scene-{index:03d}.jpg"
            try:
                with Image.open(source) as original:
                    if getattr(original, "is_animated", False):
                        original.seek(0)
                    frame = ImageOps.exif_transpose(original)
                    frame = ImageOps.fit(frame.convert("RGB"), (1920, 1080),
                                         method=Image.Resampling.LANCZOS)
                    frame.save(target, "JPEG", quality=82, optimize=True, progressive=True)
            except Exception as exc:
                raise SystemExit(f"Could not process {source.name}: {exc}") from exc
            compressed.append(target)

        quality = 82
        while True:
            with zipfile.ZipFile(args.output_zip, "w", compression=zipfile.ZIP_STORED) as archive:
                for image_path in compressed:
                    archive.write(image_path, arcname=image_path.name)
            size = args.output_zip.stat().st_size
            if size <= max_bytes or quality <= 62:
                break
            quality -= 5
            for source, target in zip(files, compressed):
                with Image.open(source) as original:
                    if getattr(original, "is_animated", False):
                        original.seek(0)
                    frame = ImageOps.exif_transpose(original)
                    frame = ImageOps.fit(frame.convert("RGB"), (1920, 1080),
                                         method=Image.Resampling.LANCZOS)
                    frame.save(target, "JPEG", quality=quality, optimize=True, progressive=True)

    size_mb = args.output_zip.stat().st_size / (1024 * 1024)
    print(f"Created {args.output_zip} with exactly 48 numbered JPG images ({size_mb:.2f} MiB, JPEG quality {quality}).")
    if size_mb > args.max_mb:
        print(f"WARNING: ZIP is still above the {args.max_mb:.1f} MiB target. Use Git command line or reduce --max-mb.")
    else:
        print(f"Ready to upload through GitHub's website (target: under {args.max_mb:.1f} MiB).")


if __name__ == "__main__":
    main()

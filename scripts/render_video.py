import subprocess, json, math, shutil, tempfile, time
from pathlib import Path

def run(cmd, timeout=300):
    last_output = ""
    for attempt in range(1, 4):
        try:
            p = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
            )
            if p.returncode == 0:
                return
            last_output = p.stdout[-5000:]
        except (subprocess.TimeoutExpired, OSError) as exc:
            last_output = str(exc)
        if attempt < 3:
            delay = attempt * 5
            print(f"FFmpeg command attempt {attempt}/3 failed; retrying in {delay}s.", flush=True)
            time.sleep(delay)

    if "-c:v" in cmd and "libx264" in cmd:
        fallback = []
        skip_next = False
        for item in cmd:
            if skip_next:
                skip_next = False
                continue
            if item in ("-preset", "-crf"):
                skip_next = True
                continue
            if item == "libx264":
                fallback.extend(["mpeg4", "-q:v", "5"])
            else:
                fallback.append(item)
        print("FFmpeg H.264 encoding failed after 3 attempts; trying MPEG-4 fallback encoder.", flush=True)
        try:
            p = subprocess.run(
                fallback, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
            )
            if p.returncode == 0:
                return
            last_output = p.stdout[-5000:]
        except (subprocess.TimeoutExpired, OSError) as exc:
            last_output = str(exc)
    raise RuntimeError("Command failed after retries:\\n" + " ".join(map(str, cmd)) + "\\n" + last_output)

def duration_seconds(audio):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(audio)],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode: raise RuntimeError("ffprobe failed: "+p.stderr)
    return float(p.stdout.strip())

def render_video(scene_dir: Path, audio_path: Path, output_path: Path, story: dict, config: dict):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed.")
    images=sorted(scene_dir.glob("scene-*.png"))
    if not images: raise RuntimeError("No scene images were generated.")
    
    width,height=int(config["width"]),int(config["height"])
    fps=int(config.get("fps",24))
    audio_len=duration_seconds(audio_path)
    per_scene=audio_len/len(images)
    
    with tempfile.TemporaryDirectory(prefix="stickman_clips_") as td:
        td=Path(td)
        clips=[]
        for i,img in enumerate(images):
            clip=td/f"clip-{i:03d}.mp4"
            frames=max(2,math.ceil(per_scene*fps))

            # Keep the image perfectly still (stable). Use veryfast here:
            # dozens of short still-image clips do not benefit much from medium
            # preset, but medium can add several minutes of silent CPU work.
            vf = f"scale={width}:{height},format=yuv420p"
            print(f"Rendering scene clip {i + 1}/{len(images)}...", flush=True)
            run(["ffmpeg","-y","-loglevel","error","-loop","1","-i",str(img),"-vf",vf,
                 "-frames:v",str(frames),"-an","-c:v","libx264","-preset","veryfast","-crf","19",str(clip)],
                timeout=300)
            clips.append(clip)
            print(f"Rendered scene clip {i + 1}/{len(images)}.", flush=True)
            
        concat=td/"concat.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips),encoding="utf-8")
        silent=td/"silent.mp4"
        print("Joining scene clips...", flush=True)
        run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(concat),
             "-c","copy","-an",str(silent)], timeout=300)
             
        print("Encoding final video and combining narration...", flush=True)
        run(["ffmpeg","-y","-loglevel","error","-i",str(silent),"-i",str(audio_path),
             "-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","19",
             "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(output_path)],
            timeout=1800)
        if not output_path.is_file() or output_path.stat().st_size < 100000:
            raise RuntimeError("FFmpeg did not produce a valid final MP4.")
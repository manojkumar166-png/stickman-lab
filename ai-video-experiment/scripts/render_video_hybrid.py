import subprocess, json, math, shutil, tempfile
from pathlib import Path

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode:
        raise RuntimeError("Command failed:\n"+" ".join(map(str,cmd))+"\n"+p.stdout[-5000:])

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
            
            # If it's an odd number scene (1, 3, 5...), we pan left-to-right.
            # If it's an even number (2, 4, 6...), we pan right-to-left.
            # This makes reused images look like a totally different shot!
            if i % 2 == 0:
                x_expr = f"(iw-iw/zoom)*(on/{frames})" # Left to Right
            else:
                x_expr = f"(iw-iw/zoom)*(1-(on/{frames}))" # Right to Left

            vf = (
                f"scale=iw*1.1:ih*1.1,setsar=1,"
                f"zoompan=z='1.05':x='{x_expr}':y='(ih-ih/zoom)/2':"
                f"d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
            )
            
            run(["ffmpeg","-y","-loglevel","error","-loop","1","-i",str(img),"-vf",vf,
                 "-frames:v",str(frames),"-an","-c:v","libx264","-preset","medium","-crf","18",str(clip)])
            clips.append(clip)
            
        concat=td/"concat.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips),encoding="utf-8")
        silent=td/"silent.mp4"
        run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(concat),
             "-c","copy","-an",str(silent)])
             
        run(["ffmpeg","-y","-loglevel","error","-i",str(silent),"-i",str(audio_path),
             "-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18",
             "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(output_path)])
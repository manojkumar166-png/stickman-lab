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
            
            # Add gentle Ken Burns motion to every scene so the video never feels like a
            # slideshow of frozen images. Alternate slow zoom-in and zoom-out framing.
            zoom_expr = "min(zoom+0.0007,1.08)" if i % 2 == 0 else "if(lte(zoom,1.0),1.08,max(1.0,zoom-0.0007))"
            x_expr = "iw/2-(iw/zoom/2)" if i % 2 == 0 else "(iw-iw/zoom)*(on/%d)" % max(frames-1,1)
            y_expr = "ih/2-(ih/zoom/2)"
            vf = f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2},zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps={fps},format=yuv420p"
            run(["ffmpeg","-y","-loglevel","error","-loop","1","-i",str(img),"-vf",vf,
                 "-frames:v",str(frames),"-an","-c:v","libx264","-preset","veryfast","-crf","19",str(clip)])
            clips.append(clip)
            
        concat=td/"concat.txt"
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips),encoding="utf-8")
        silent=td/"silent.mp4"
        run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(concat),
             "-c","copy","-an",str(silent)])
             
        run(["ffmpeg","-y","-loglevel","error","-i",str(silent),"-i",str(audio_path),
             "-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18",
             "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(output_path)])
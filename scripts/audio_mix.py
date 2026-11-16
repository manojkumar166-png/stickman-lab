#!/usr/bin/env python3
"""Create a restrained, synthetic sound-effects-only mix for the cinematic short.
No voiceover and no music. The repository does not contain Claude's original field recordings.
"""
import argparse
import subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    cues=[
        (3.15,82,.70),(5.55,118,.18),(6.35,105,.18),(7.15,94,.18),
        (8.55,520,.20),(9.05,170,.95),(24.85,880,.16),(28.10,145,.32)
    ]
    cmd=["ffmpeg","-y","-loglevel","error","-i",a.input,
         "-f","lavfi","-t","30","-i","anoisesrc=color=pink:amplitude=0.012:sample_rate=48000"]
    for _,freq,dur in cues:
        cmd += ["-f","lavfi","-t",str(dur),"-i",f"sine=frequency={freq}:sample_rate=48000"]
    filters=["[1:a]lowpass=f=380,volume=0.42[bed]"]
    labels=["[bed]"]
    for i,(when,freq,dur) in enumerate(cues):
        idx=i+2
        filters.append(f"[{idx}:a]afade=t=out:st={max(0,dur-.08):.3f}:d=0.08,volume=0.22,adelay={int(when*1000)}|{int(when*1000)}[s{i}]")
        labels.append(f"[s{i}]")
    filters.append("".join(labels)+f"amix=inputs={len(labels)}:duration=longest:normalize=0,alimiter=limit=0.88[aout]")
    cmd += ["-filter_complex",";".join(filters),"-map","0:v:0","-map","[aout]",
            "-c:v","copy","-c:a","aac","-b:a","160k","-shortest","-movflags","+faststart",a.output]
    subprocess.run(cmd,check=True)
    print(f"Audio mix written: {a.output} (synthetic room tone and SFX; no music or speech)")

if __name__=="__main__":
    main()

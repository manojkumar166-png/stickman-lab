import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright";
const root="stickman-films/latest",previewOnly=process.argv.includes("--preview-only");
const run=(cmd,args)=>{const r=spawnSync(cmd,args,{stdio:"inherit"});if(r.status!==0)throw new Error(cmd+" failed with exit "+r.status)};
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
try{
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 await page.setContent('<!doctype html><html><body style="margin:0;background:#171322"><canvas id="film" width="1920" height="1080"></canvas></body></html>');
 await page.addScriptTag({type:"module",path:path.resolve("scripts/film.js")});
 await page.waitForFunction(()=>typeof window.renderAt==="function"&&window.FILM);
 const film=await page.evaluate(()=>window.FILM);fs.mkdirSync(root,{recursive:true});
 fs.writeFileSync(path.join(root,"film.json"),JSON.stringify(film,null,2)+"\n");fs.writeFileSync(path.join(root,"title.txt"),film.title+"\n");
 const canvas=page.locator("#film"),samples=film.cuts.slice(0,-1).map(f=>Math.min(29.9,f/30+.8));
 for(let i=0;i<samples.length;i++){await page.evaluate(t=>window.renderAt(document.querySelector("#film"),t),samples[i]);await canvas.screenshot({path:path.join(root,"preview-"+String(i+1).padStart(2,"0")+".jpg"),type:"jpeg",quality:90});}
 run("ffmpeg",["-y","-loglevel","error","-pattern_type","glob","-i",path.join(root,"preview-*.jpg"),"-filter_complex","tile=3x3:padding=18:margin=18:color=0x21172f","-frames:v","1",path.join(root,"contact-sheet.jpg")]);
 if(previewOnly){console.log("PREVIEW READY: "+path.join(root,"contact-sheet.jpg"));process.exit(0);}
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"stickman-frames-"));
 try{for(let frame=0;frame<film.dur*film.fps;frame++){await page.evaluate(({f,fps})=>window.renderAt(document.querySelector("#film"),f/fps),{f:frame,fps:film.fps});await canvas.screenshot({path:path.join(tmp,String(frame).padStart(5,"0")+".jpg"),type:"jpeg",quality:92});if(frame%90===0)console.log("Rendered "+frame+"/"+(film.dur*film.fps)+" frames");}
 run("ffmpeg",["-y","-loglevel","error","-framerate",String(film.fps),"-i",path.join(tmp,"%05d.jpg"),"-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-r",String(film.fps),"-c:v","libx264","-preset","medium","-crf","19","-movflags","+faststart",path.join(root,"video-silent.mp4")]);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
 run("python",["scripts/audio_mix.py","--input",path.join(root,"video-silent.mp4"),"--output",path.join(root,"video.mp4")]);
 run("ffprobe",["-v","error","-show_entries","format=duration,size:stream=codec_name,width,height,r_frame_rate","-of","json",path.join(root,"video.mp4")]);
 console.log("FINAL MP4: "+path.join(root,"video.mp4"));
}finally{await browser.close()}

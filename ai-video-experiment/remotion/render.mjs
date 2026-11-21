import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {execFileSync} from "node:child_process";
import {bundle} from "@remotion/bundler";
import {selectComposition, renderMedia} from "@remotion/renderer";

const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,"../..");
const outputDir=path.join(root,"output");
const runKey=process.argv[2];
if(!runKey || !/^[a-zA-Z0-9-]+$/.test(runKey)) throw new Error("A valid AI experiment run key is required.");
const sceneDir=path.join(outputDir,`scenes-${runKey}`);
const audioPath=path.join(outputDir,`narration-${runKey}.mp3`);
const storyPath=path.join(outputDir,`story-${runKey}.json`);
const publicDir=path.join(here,"public");
const imageDir=path.join(publicDir,"scenes");
fs.rmSync(publicDir,{recursive:true,force:true});
fs.mkdirSync(imageDir,{recursive:true});
if(!fs.existsSync(audioPath) || !fs.existsSync(storyPath)) throw new Error("Narration or story checkpoint is missing.");
const story=JSON.parse(fs.readFileSync(storyPath,"utf8"));
const sourceImages=fs.readdirSync(sceneDir).filter(name=>/^scene-\d+\.png$/.test(name)).sort();
if(!sourceImages.length || sourceImages.length!==story.scenes.length) throw new Error("Scene image count does not match the saved story.");
const scenes=sourceImages.map((name,index)=>{
  const source=path.join(sceneDir,name);
  if(fs.statSync(source).size<1000) throw new Error(`Scene image is empty: ${source}`);
  const target=`scenes/${name}`;
  fs.copyFileSync(source,path.join(publicDir,target));
  return {image:target,heading:String(story.scenes[index]?.heading || story.scenes[index]?.title || `Scene ${index+1}`)};
});
const duration=Number(execFileSync("ffprobe",["-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",audioPath],{encoding:"utf8"}).trim());
if(!Number.isFinite(duration)||duration<=0) throw new Error("Narration duration is invalid.");
fs.copyFileSync(audioPath,path.join(publicDir,"narration.mp3"));
const sceneFrames=Math.max(24,Math.ceil(duration*24/scenes.length));
const inputProps={scenes,audio:"narration.mp3",sceneFrames};
const serveUrl=await bundle({entryPoint:path.join(here,"src","index.jsx"),publicDir});
const composition=await selectComposition({serveUrl,id:"AIExperiment",inputProps});
const output=path.join(outputDir,`remotion-${runKey}.mp4`);
const temporary=output+".rendering.mp4";
fs.rmSync(temporary,{force:true});
await renderMedia({
  composition,serveUrl,codec:"h264",outputLocation:temporary,inputProps,
  pixelFormat:"yuv420p",crf:20,concurrency:2,
  onProgress:({progress})=>{const pct=Math.round(progress*100);if(pct%10===0)console.log(`Remotion progress: ${pct}%`);}
});
const streams=execFileSync("ffprobe",["-v","error","-show_entries","stream=codec_type","-of","csv=p=0",temporary],{encoding:"utf8"});
if(!streams.includes("video")||!streams.includes("audio")||fs.statSync(temporary).size<100000){
  fs.rmSync(temporary,{force:true});
  throw new Error("Remotion output failed video/audio validation.");
}
fs.renameSync(temporary,output);
console.log(`Remotion video ready: ${output}`);

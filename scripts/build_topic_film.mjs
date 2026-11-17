import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { chromium } from "playwright";

const root="stickman-films/latest";
const run=(cmd,args)=>{const r=spawnSync(cmd,args,{stdio:"inherit"});if(r.status!==0)throw new Error(cmd+" failed with exit "+r.status);};
const film=JSON.parse(fs.readFileSync(path.join(root,"film.json"),"utf8"));
if(!Array.isArray(film.scenes)||film.scenes.length!==9||film.duration!==30)throw new Error("Film brief failed validation");
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
try{
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
 await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#21182f"><canvas id="film" width="1920" height="1080"></canvas></body></html>');
 await page.addScriptTag({content:"("+drawFilm.toString()+")()"});
 await page.evaluate(data=>window.setupFilm(data),film);
 const canvas=page.locator("#film");fs.mkdirSync(root,{recursive:true});
 fs.writeFileSync(path.join(root,"film.json"),JSON.stringify(film,null,2)+"\n");
 fs.writeFileSync(path.join(root,"title.txt"),film.title+"\n");
 for(let i=0;i<film.scenes.length;i++){
  const scene=film.scenes[i],t=scene.start+Math.min(.8,(scene.end-scene.start)/3);
  await page.evaluate(t=>window.renderAt(t),t);
  await canvas.screenshot({path:path.join(root,"preview-"+String(i+1).padStart(2,"0")+".jpg"),type:"jpeg",quality:91});
 }
 run("ffmpeg",["-y","-loglevel","error","-pattern_type","glob","-i",path.join(root,"preview-*.jpg"),"-filter_complex","tile=3x3:padding=18:margin=18:color=0x21172f","-frames:v","1",path.join(root,"contact-sheet.jpg")]);
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"daily-stickman-"));
 try{
  const total=film.duration*film.fps;
  for(let frame=0;frame<total;frame++){
   await page.evaluate(t=>window.renderAt(t),frame/film.fps);
   await canvas.screenshot({path:path.join(tmp,String(frame).padStart(5,"0")+".jpg"),type:"jpeg",quality:90});
   if(frame%90===0)console.log("Rendered "+frame+"/"+total+" frames");
  }
  run("ffmpeg",["-y","-loglevel","error","-framerate",String(film.fps),"-i",path.join(tmp,"%05d.jpg"),"-vf","scale=1920:1080:flags=lanczos,format=yuv420p","-r",String(film.fps),"-c:v","libx264","-preset","medium","-crf","19","-movflags","+faststart",path.join(root,"video-silent.mp4")]);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
 run("python",["scripts/audio_mix.py","--input",path.join(root,"video-silent.mp4"),"--output",path.join(root,"video.mp4")]);
 const probe=spawnSync("ffprobe",["-v","error","-show_entries","format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate","-of","json",path.join(root,"video.mp4")],{encoding:"utf8"});
 if(probe.status!==0)throw new Error("ffprobe could not inspect rendered MP4");
 const report=JSON.parse(probe.stdout),video=report.streams.find(s=>s.codec_type==="video"),duration=Number(report.format.duration);
 if(!video||video.codec_name!=="h264"||video.width!==1920||video.height!==1080||video.r_frame_rate!=="30/1"||duration<29.9||duration>30.1)throw new Error("MP4 audit failed: "+JSON.stringify({video,duration}));
 fs.writeFileSync(path.join(root,"video-audit.json"),JSON.stringify({status:"PASS",duration_seconds:duration,width:video.width,height:video.height,fps:video.r_frame_rate,codec:video.codec_name,size_bytes:Number(report.format.size)},null,2)+"\n");
 console.log("PASS: "+film.title+" — H.264 1920x1080 30fps "+duration.toFixed(3)+"s");
}finally{await browser.close();}

function drawFilm(){
 const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
 const smooth=v=>{v=clamp(v);return v*v*(3-2*v);};
 const line=(c,x,y,X,Y,color,w=12)=>{c.beginPath();c.moveTo(x,y);c.lineTo(X,Y);c.strokeStyle=color;c.lineWidth=w;c.lineCap="round";c.stroke();};
 const circle=(c,x,y,r,color)=>{c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fillStyle=color;c.fill();};
 const box=(c,x,y,w,h,r,color)=>{c.fillStyle=color;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();};
 function prop(c,k,x,y,t){
  c.save();c.translate(x,y);c.shadowColor="rgba(255,190,125,.5)";c.shadowBlur=32;
  const ivory="#F5D6A7",teal="#55B7AC",coral="#FF796B";
  switch(k){
   case "door":box(c,-95,-190,190,380,16,"#176E70");c.strokeStyle=ivory;c.lineWidth=10;c.strokeRect(-95,-190,190,380);circle(c,62,8,12,ivory);break;
   case "phone":box(c,-90,-160,180,320,24,"#28243D");box(c,-75,-140,150,280,15,"#F6EBDD");box(c,-55,-85,105,42,12,"#CFC7C2");box(c,-5,-20,65,50,12,coral);break;
   case "umbrella":c.beginPath();c.arc(0,0,140,Math.PI,0);c.quadraticCurveTo(105,125,70,48);c.quadraticCurveTo(35,125,0,48);c.quadraticCurveTo(-35,125,-70,48);c.quadraticCurveTo(-105,125,-140,0);c.closePath();c.fillStyle=coral;c.fill();line(c,0,0,0,190,ivory,13);break;
   case "plant":box(c,-80,65,160,115,18,"#C87962");line(c,0,70,0,-110,teal,15);for(const a of [-1,1]){c.beginPath();c.ellipse(a*50,-65,48,22,a*.3,0,Math.PI*2);c.fillStyle=teal;c.fill();}break;
   case "clock":circle(c,0,0,145,ivory);circle(c,0,0,126,"#40344C");for(let i=0;i<12;i++){const a=i*Math.PI/6;circle(c,Math.sin(a)*105,-Math.cos(a)*105,5,ivory);}line(c,0,0,0,-78,ivory,12);line(c,0,0,70,30,coral,12);break;
   case "book":box(c,-135,-120,270,240,18,coral);line(c,0,-110,0,112,ivory,8);for(let i=0;i<4;i++)line(c,-95,-65+i*42,-20,-65+i*42,ivory,5);break;
   case "cup":box(c,-85,-75,150,170,20,"#E7D5BD");c.beginPath();c.arc(70,-5,48,-Math.PI/2,Math.PI/2);c.strokeStyle=ivory;c.lineWidth=15;c.stroke();break;
   case "star":c.beginPath();for(let i=0;i<10;i++){const a=-Math.PI/2+i*Math.PI/5,r=i%2?62:145;c.lineTo(Math.cos(a)*r,Math.sin(a)*r);}c.closePath();c.fillStyle=ivory;c.fill();break;
   case "planet":circle(c,0,0,100,"#D98E79");c.beginPath();c.ellipse(0,0,170,55,-.3,0,Math.PI*2);c.strokeStyle=ivory;c.lineWidth=18;c.stroke();break;
   case "tree":box(c,-28,20,56,180,12,"#A96C52");for(const [a,b,r] of [[0,-75,85],[-65,-20,65],[65,-20,65]])circle(c,a,b,r,teal);break;
   case "animal":circle(c,0,0,90,"#D8A47B");c.beginPath();c.moveTo(-62,-55);c.lineTo(-100,-145);c.lineTo(-15,-95);c.fillStyle="#D8A47B";c.fill();c.beginPath();c.moveTo(62,-55);c.lineTo(100,-145);c.lineTo(15,-95);c.fill();circle(c,-30,-5,8,"#30253D");circle(c,30,-5,8,"#30253D");break;
   case "train":box(c,-160,-95,320,185,28,"#398D91");for(let i=0;i<3;i++)box(c,-125+i*95,-65,72,65,9,"#F3D8AF");circle(c,-85,105,28,"#29243A");circle(c,90,105,28,"#29243A");break;
   case "bridge":line(c,-165,100,165,100,ivory,18);c.beginPath();c.arc(0,100,125,Math.PI,Math.PI*2);c.strokeStyle=teal;c.lineWidth=20;c.stroke();for(let i=-2;i<=2;i++)line(c,i*48,100,i*48,0,ivory,7);break;
   case "cloud":for(const [a,b,r] of [[-75,20,70],[0,-35,90],[80,20,68]])circle(c,a,b,r,"#E8E3DF");break;
   case "heart":c.beginPath();c.moveTo(0,125);c.bezierCurveTo(-210,0,-125,-150,0,-55);c.bezierCurveTo(125,-150,210,0,0,125);c.fillStyle=coral;c.fill();break;
   case "lightbulb":circle(c,0,-45,100,ivory);box(c,-52,45,104,95,18,"#C98C61");for(let i=0;i<8;i++){const a=i*Math.PI/4;line(c,Math.cos(a)*135,Math.sin(a)*135,Math.cos(a)*175,Math.sin(a)*175,ivory,9);}break;
  }c.restore();
 }
 function hero(c,x,t,mood,reach){
  c.save();c.translate(x,855);const bob=Math.sin(t*3.2)*4;
  circle(c,0,0,55,"rgba(12,8,24,.25)");line(c,-18,-150,-38+Math.sin(t*4)*10,-10,"#29263D",24);line(c,18,-150,38-Math.sin(t*4)*10,-10,"#29263D",24);
  box(c,-62,-355+bob,124,220,38,"#FF6B5E");line(c,-48,-310,-(reach?110:88),-220,"#FF6B5E",24);line(c,48,-310,reach?150:92,-(reach?245:220),"#FF6B5E",24);
  circle(c,reach?150:92,-(reach?245:220),14,"#F8E9CC");circle(c,0,-445+bob,78,"#F8E9CC");circle(c,-27,-455+bob,7,"#332B35");circle(c,27,-455+bob,7,"#332B35");
  if(mood==="happy"){c.beginPath();c.arc(0,-428+bob,25,.12*Math.PI,.88*Math.PI);c.strokeStyle="#A65D5A";c.lineWidth=6;c.stroke();}
  else if(mood==="sad"){line(c,-15,-405+bob,15,-405+bob,"#A65D5A",6);line(c,-38,-482+bob,-12,-490+bob,"#49343A",6);line(c,12,-490+bob,38,-482+bob,"#49343A",6);}
  else line(c,-12,-415+bob,12,-415+bob,"#A65D5A",5);c.restore();
 }
 function setupFilm(f){window.renderAt=t=>renderAt(f,t);}
 function renderAt(f,t){
  const c=document.querySelector("#film").getContext("2d"),w=1920,h=1080;
  let i=f.scenes.findIndex(s=>t>=s.start&&t<s.end);if(i<0)i=8;const s=f.scenes[i],u=clamp((t-s.start)/(s.end-s.start));
  const colors=[["#30243E","#17172B"],["#493047","#21182F"],["#31505A","#172B3B"],["#61404A","#281D36"],["#3B5260","#1C283B"],["#4D3A58","#201A35"],["#59404A","#241C32"],["#38545A","#182A38"],["#A96F69","#392D4A"]];
  const g=c.createLinearGradient(0,0,0,h);g.addColorStop(0,colors[i][0]);g.addColorStop(1,colors[i][1]);c.fillStyle=g;c.fillRect(0,0,w,h);
  c.fillStyle="rgba(255,224,190,.08)";c.fillRect(0,0,w,760);for(let n=0;n<12;n++){c.fillStyle="rgba(255,220,185,.09)";c.fillRect(100+n*165,420+(n%3)*55,75,350);}
  c.fillStyle="#30243B";c.fillRect(0,850,w,230);c.fillStyle="rgba(255,197,135,.12)";c.fillRect(0,842,w,10);
  c.save();c.translate(w/2,h/2);const zoom=1+.025*Math.sin(u*Math.PI);c.scale(zoom,zoom);c.translate(-w/2,-h/2);
  const hx=i===2?610+210*smooth(u):i===7?760:650;hero(c,hx,t,s.emotion,i>=2&&i<=7);circle(c,1320,520,245,"rgba(255,190,125,.08)");prop(c,s.visual,1320,520,t);c.restore();
  c.fillStyle="rgba(9,7,18,.38)";c.fillRect(0,0,w,120);c.fillStyle="#F8E9D5";c.font="600 31px Arial,sans-serif";c.fillText(f.title.toUpperCase(),90,76);
  c.fillStyle="rgba(12,9,22,.68)";c.fillRect(0,900,w,180);c.fillStyle="#FFB69B";c.font="700 27px Arial,sans-serif";c.fillText("SCENE "+String(i+1).padStart(2,"0")+" / 09",95,958);
  c.fillStyle="#FFF2E4";c.font="500 43px Arial,sans-serif";c.fillText(s.title,95,1020);
  if(t<2.2){c.fillStyle="rgba(255,245,230,.92)";c.font="700 56px Arial,sans-serif";c.fillText(f.premise.slice(0,82),95,165);}
  if(t>=27.2){c.fillStyle="rgba(20,15,31,.82)";c.fillRect(0,0,w,h);c.fillStyle="#FFE8C9";c.textAlign="center";c.font="700 72px Arial,sans-serif";c.fillText(f.end_card,960,520);c.font="500 28px Arial,sans-serif";c.fillText(f.title,960,585);c.textAlign="left";}
  const v=c.createRadialGradient(960,530,360,960,530,1150);v.addColorStop(0,"rgba(0,0,0,0)");v.addColorStop(1,"rgba(8,5,18,.35)");c.fillStyle=v;c.fillRect(0,0,w,h);
 }
 window.setupFilm=setupFilm;
}

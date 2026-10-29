"""Render original storybook scenes with HTML/CSS and JavaScript; no image-generation API."""
from __future__ import annotations
import asyncio, json, html
from pathlib import Path
from playwright.async_api import async_playwright

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:WIDTHpx;height:HEIGHTpx;overflow:hidden}
.scene{position:relative;width:WIDTHpx;height:HEIGHTpx;overflow:hidden;background:linear-gradient(180deg,#7eb8d1 0%,#c6d9c6 48%,#f2c98e 100%);font-family:Georgia,serif;color:#fff7d9}.scene.ocean{background:linear-gradient(180deg,#74b9d0 0%,#2f829e 52%,#164e68 100%)}.scene.space{background:radial-gradient(ellipse at 70% 20%,#293f70,#111b39 65%,#090f24)}.scene.lab{background:linear-gradient(135deg,#c8dedb,#8eb8b5 48%,#537e83)}.scene.desert{background:linear-gradient(180deg,#8ac4d4,#edc18b 60%,#b87952)}.scene.city{background:linear-gradient(180deg,#91c8d8,#e9c39a 60%,#758b83)}.scene.home{background:linear-gradient(180deg,#c7d8d0,#e8c89e 60%,#8a735e)}.scene.cave{background:linear-gradient(180deg,#263d49,#5e6d68 55%,#1d2a30)}.scene.mountain{background:linear-gradient(180deg,#9cc8d6,#d5d7b5 52%,#648b83)}.scene.forest{background:linear-gradient(180deg,#9bc9d0,#9ab68c 50%,#315c48)}.scene.ocean .tree,.scene.space .tree,.scene.lab .tree,.scene.cave .tree{display:none}.scene.space .sun{background:#fff1c9;box-shadow:0 0 65px #fff1c966}.scene.ocean .field{background:linear-gradient(180deg,#60c4d0,#1e718d)}.scene.cave .sun,.scene.cave .cloud,.scene.cave .mountain{display:none}.scene.magnet{background:radial-gradient(ellipse at 50% 38%,#315b7b 0%,#17354f 62%,#0b1d30 100%)}.scene.magnet .sun,.scene.magnet .cloud,.scene.magnet .mountain,.scene.magnet .hill,.scene.magnet .field,.scene.magnet .tree{display:none}.scene.winter{background:linear-gradient(180deg,#344d70 0%,#a7c7d5 55%,#e6edf0 100%)}.winter .sun{background:radial-gradient(circle at 35% 32%,#fff,#dcebf0 70%,#b5d2df);box-shadow:0 0 65px #e5f6ff88}.winter .mountain{background:#c2d5df}.winter .hill.back{background:linear-gradient(150deg,#e4edf0,#b7d0db)}.winter .hill{background:linear-gradient(160deg,#e9f0f2,#b7cbd5 80%)}.winter .field{background:linear-gradient(180deg,#f5f7f6,#d5e2e8)}.winter .tree:before{background:radial-gradient(circle at 36% 30%,#d9e8e7,#65828a 72%);box-shadow:35px 20px 0 -15px #78959d,-25px 30px 0 -20px #9bb8c0}.winter .tree:after{background:#c9dfe3}
.skyglow{position:absolute;inset:0;background:radial-gradient(ellipse at 72% 24%,#fff4c8aa 0,transparent 26%),linear-gradient(180deg,#a8d0dc33,transparent 60%)}
.sun{position:absolute;width:110px;height:110px;border-radius:50%;left:72%;top:13%;background:radial-gradient(circle at 35% 32%,#fff5cc,#f6d18b 65%,#e9a875);box-shadow:0 0 70px #fff0bd88}
.cloud{position:absolute;width:240px;height:40px;border-radius:50%;background:#fff4dcbb;filter:blur(1px);top:20%;left:12%;box-shadow:36px -14px 0 3px #fff4dcbb,75px 2px 0 -4px #fff4dcbb}
.cloud.c2{top:31%;left:49%;transform:scale(.65);opacity:.75}
.mountain{position:absolute;left:-8%;width:116%;height:47%;bottom:23%;background:#91ad91;clip-path:polygon(0 70%,12% 30%,22% 58%,35% 8%,48% 62%,60% 28%,72% 61%,84% 16%,100% 65%,100% 100%,0 100%);opacity:.82}
.hill{position:absolute;left:-10%;width:125%;height:35%;bottom:12%;border-radius:50% 50% 0 0;background:linear-gradient(160deg,#72966e,#426b59 80%);transform:rotate(-3deg)}
.hill.back{bottom:18%;left:34%;height:27%;background:linear-gradient(150deg,#a2b77e,#648665);transform:rotate(5deg)}
.field{position:absolute;bottom:-7%;left:-5%;width:115%;height:28%;background:linear-gradient(180deg,#64845a,#344f43);border-radius:48% 48% 0 0}
.tree{position:absolute;bottom:17%;width:30px;height:180px;background:#604b3d;border-radius:35% 35% 5px 5px;transform:rotate(3deg)}
.tree:before,.tree:after{content:"";position:absolute;border-radius:50%;background:radial-gradient(circle at 36% 30%,#b2c58b,#52795a 72%);width:140px;height:130px;left:-55px;top:-70px;box-shadow:35px 20px 0 -15px #3e6a50,-25px 30px 0 -20px #729566}
.tree:after{width:95px;height:95px;left:-30px;top:-105px;background:#89aa76;opacity:.8}
.t1{left:7%;transform:scale(1.05)}.t2{right:8%;transform:scale(1.3)}.t3{left:20%;transform:scale(.6);opacity:.7}
.vignette{position:absolute;inset:0;background:linear-gradient(90deg,#1a2a2b44,transparent 50%,#1a2a2b22),linear-gradient(0deg,#142b26aa,transparent 50%);pointer-events:none}
.paper{position:absolute;inset:0;opacity:.13;pointer-events:none;background-image:radial-gradient(#fff 0.55px,transparent .8px);background-size:5px 5px;mix-blend-mode:soft-light}
.kicker{position:absolute;top:34px;left:5%;max-width:90%;font:800 17px/1.2 system-ui,sans-serif;letter-spacing:2px;text-transform:uppercase;color:#fff;text-shadow:0 3px 5px #000,0 0 12px #000}
.title{position:absolute;left:5%;top:68px;width:90%;font:900 36px/1.08 system-ui,sans-serif;color:#ffe94d;text-transform:uppercase;text-shadow:2px 2px 0 #111,-2px -2px 0 #111,2px -2px 0 #111,-2px 2px 0 #111,0 5px 12px #000}
.narration{position:absolute;left:5%;bottom:7%;width:90%;font:900 27px/1.18 system-ui,sans-serif;text-align:center;color:#fff;text-shadow:2px 2px 0 #111,-2px -2px 0 #111,2px -2px 0 #111,-2px 2px 0 #111,0 4px 9px #000;letter-spacing:.2px}
.index{position:absolute;right:5%;top:36px;font:800 13px system-ui,sans-serif;letter-spacing:2px;color:#fff;text-shadow:0 2px 5px #000}
#science{position:absolute;inset:0;width:100%;height:100%}
</style></head><body><main class="scene SCENECLASS"><div class="skyglow"></div><div class="sun"></div><div class="cloud"></div><div class="cloud c2"></div><div class="mountain"></div><div class="hill back"></div><div class="hill"></div><div class="field"></div><div class="tree t1"></div><div class="tree t2"></div><div class="tree t3"></div><canvas id="science"></canvas><div class="vignette"></div><div class="paper"></div><div class="kicker">SCIENCE SHORT</div><div class="title">TITLE</div><div class="narration">CAPTION</div><div class="index">INDEX</div></main><script>
const c=document.getElementById('science'),ctx=c.getContext('2d');c.width=WIDTH;c.height=HEIGHT;
const topic=TOPIC.toLowerCase(); const sceneText=SCENETEXT.toLowerCase(); const sceneNo=SCENENO; const cx=c.width*(.52+((sceneNo%4)*.055)), cy=c.height*(.39+((sceneNo%3)*.055));
function line(x1,y1,x2,y2,color='#fff1bd',w=3){ctx.strokeStyle=color;ctx.lineWidth=w;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()}
function glow(x,y,r,color){const g=ctx.createRadialGradient(x,y,2,x,y,r);g.addColorStop(0,color);g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()}
if(/magnet|magnetic|compass|pole|attract|repel|iron filing|field line/.test(sceneText+" "+topic)){
const mx=c.width*.5,my=c.height*.43, t=sceneText;
if(/compass|direction|north|south pole/.test(t)){
ctx.fillStyle="#f2e7c9";ctx.beginPath();ctx.arc(mx,my,104,0,Math.PI*2);ctx.fill();ctx.strokeStyle="#29465c";ctx.lineWidth=5;ctx.beginPath();ctx.arc(mx,my,85,0,Math.PI*2);ctx.stroke();
ctx.fillStyle="#d94f50";ctx.beginPath();ctx.moveTo(mx,my-67);ctx.lineTo(mx-13,my+8);ctx.lineTo(mx,my);ctx.lineTo(mx+13,my+8);ctx.closePath();ctx.fill();ctx.fillStyle="#456f9c";ctx.beginPath();ctx.moveTo(mx,my+67);ctx.lineTo(mx-13,my-8);ctx.lineTo(mx,my);ctx.lineTo(mx+13,my-8);ctx.closePath();ctx.fill();
}else if(/paper clip|paperclip|iron filing|attract|pull|metal object/.test(t)){
ctx.fillStyle="#e45155";ctx.fillRect(mx-90,my-58,90,48);ctx.fillStyle="#e8e9e5";ctx.fillRect(mx,my-58,90,48);ctx.fillStyle="#fff";ctx.font="bold 24px sans-serif";ctx.textAlign="center";ctx.fillText("N",mx-45,my-27);ctx.fillText("S",mx+45,my-27);
for(let k=0;k<9;k++){let x=mx-180+k*45,y=my+45+(k%3)*27;ctx.strokeStyle="#d7e5eb";ctx.lineWidth=5;ctx.beginPath();ctx.ellipse(x,y,10,19,.2,0,Math.PI*2);ctx.stroke()}
}else if(/repel|same pole|like pole|push apart/.test(t)){
for(const dx of [-100,100]){ctx.fillStyle="#e45155";ctx.fillRect(mx+dx-55,my-35,110,70);ctx.fillStyle="#fff";ctx.font="bold 25px sans-serif";ctx.textAlign="center";ctx.fillText("N",mx+dx,my+9)}
}else{
ctx.fillStyle="#e45155";ctx.fillRect(mx-115,my-35,115,70);ctx.fillStyle="#e8e9e5";ctx.fillRect(mx,my-35,115,70);ctx.fillStyle="#fff";ctx.font="bold 28px sans-serif";ctx.textAlign="center";ctx.fillText("N",mx-58,my+10);ctx.fillStyle="#17354f";ctx.fillText("S",mx+58,my+10);ctx.strokeStyle="#8dd9f3";ctx.lineWidth=3;
for(let k=0;k<5;k++){ctx.beginPath();ctx.ellipse(mx,my,145+k*22,70+k*20,0,Math.PI,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.ellipse(mx,my,145+k*22,70+k*20,0,0,Math.PI);ctx.stroke()}
}}
else if(/ocean|sea|salty|whale|fish|coral|water cycle|underwater/.test(sceneText+" "+topic)){ctx.fillStyle='#75d2d1';for(let j=0;j<5;j++){ctx.beginPath();ctx.ellipse(c.width*(.2+j*.17),c.height*(.63+(j%2)*.08),75,13,0,0,Math.PI*2);ctx.fill()}ctx.strokeStyle='#d9f4e8';ctx.lineWidth=4;for(let j=0;j<4;j++){ctx.beginPath();ctx.moveTo(cx-130,cy+30+j*25);ctx.quadraticCurveTo(cx-70,cy+5+j*25,cx-10,cy+30+j*25);ctx.stroke()}if(/fish|whale/.test(sceneText)){ctx.fillStyle='#f3c17b';ctx.beginPath();ctx.ellipse(cx,cy,58,30,0,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.moveTo(cx-48,cy);ctx.lineTo(cx-82,cy-24);ctx.lineTo(cx-82,cy+24);ctx.fill();ctx.fillStyle='#183d52';ctx.beginPath();ctx.arc(cx+32,cy-7,4,0,Math.PI*2);ctx.fill()}}
else if(/airplane|aircraft|flight|fly|wing|lift/.test(sceneText+" "+topic)){ctx.save();ctx.translate(cx,cy);ctx.rotate(-.12);ctx.fillStyle='#f3ead1';ctx.beginPath();ctx.moveTo(-125,0);ctx.lineTo(-20,-10);ctx.lineTo(20,-68);ctx.lineTo(42,-66);ctx.lineTo(28,-8);ctx.lineTo(118,8);ctx.lineTo(120,22);ctx.lineTo(24,15);ctx.lineTo(8,48);ctx.lineTo(-10,48);ctx.lineTo(-12,12);ctx.lineTo(-125,8);ctx.closePath();ctx.fill();line(-145,60,120,60,'#fff1bd',2);line(-125,78,75,78,'#fff1bd',2);ctx.restore()}
else if(/bee|pollinat|hive|honey/.test(sceneText+" "+topic)){ctx.fillStyle='#eebf54';ctx.beginPath();ctx.ellipse(cx,cy,43,28,0,0,Math.PI*2);ctx.fill();ctx.fillStyle='#4b4b3e';ctx.fillRect(cx-18,cy-25,9,50);ctx.fillRect(cx+5,cy-26,9,52);ctx.fillStyle='#e6f2e9';ctx.beginPath();ctx.ellipse(cx-12,cy-34,20,11,-.5,0,Math.PI*2);ctx.ellipse(cx+20,cy-34,20,11,.5,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#f9e4a9';ctx.lineWidth=2;ctx.beginPath();ctx.arc(cx,cy,78,0,Math.PI*2);ctx.stroke()}
else if(/cloud|rain|storm|weather|water cycle/.test(sceneText+" "+topic)){ctx.fillStyle='#e8f0e8';for(const [dx,dy,r] of [[-35,0,36],[0,-20,45],[37,0,33]]){ctx.beginPath();ctx.arc(cx+dx,cy+dy,r,0,Math.PI*2);ctx.fill()}for(let j=0;j<7;j++){line(cx-48+j*16,cy+42,cx-58+j*16,cy+62,'#8bd8e8',3)}glow(cx+135,cy-70,55,'#ffe5a0aa')}
else if(/volcano|eruption|lava|magma/.test(sceneText+" "+topic)){ctx.fillStyle='#8b6253';ctx.beginPath();ctx.moveTo(cx-150,cy+105);ctx.lineTo(cx-40,cy-100);ctx.lineTo(cx+10,cy-30);ctx.lineTo(cx+70,cy-112);ctx.lineTo(cx+155,cy+105);ctx.closePath();ctx.fill();ctx.fillStyle='#f28a55';ctx.beginPath();ctx.moveTo(cx-42,cy-95);ctx.lineTo(cx+8,cy-27);ctx.lineTo(cx+70,cy-108);ctx.lineTo(cx+44,cy-42);ctx.lineTo(cx-15,cy-42);ctx.closePath();ctx.fill();for(let j=0;j<18;j++){ctx.fillStyle=j%2?'#ffd17c':'#ef8051';ctx.beginPath();ctx.arc(cx-55+(j*47)%130,cy-130+(j*31)%75,3+j%5,0,Math.PI*2);ctx.fill()}}
else if(/magnet|magnetic|compass/.test(sceneText+" "+topic)){ctx.lineWidth=24;ctx.lineCap='butt';ctx.strokeStyle='#d96e64';ctx.beginPath();ctx.moveTo(cx-65,cy-65);ctx.lineTo(cx-65,cy+35);ctx.arc(cx,cy+35,65,Math.PI,0,true);ctx.lineTo(cx+65,cy-65);ctx.stroke();ctx.strokeStyle='#dce6d9';ctx.beginPath();ctx.moveTo(cx,cy+100);ctx.lineTo(cx,cy+140);ctx.stroke();ctx.strokeStyle='#f4d18c';for(let j=0;j<12;j++){let x=cx-115+j*21,y=cy+130+(j%3)*12;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+8,y-7);ctx.stroke()}}
else if(/brain|memory|neuron|nerve/.test(sceneText+" "+topic)){ctx.fillStyle='#e6a9a0';ctx.beginPath();ctx.arc(cx-35,cy-8,47,0,Math.PI*2);ctx.arc(cx+15,cy-40,43,0,Math.PI*2);ctx.arc(cx+55,cy+1,42,0,Math.PI*2);ctx.arc(cx+8,cy+33,43,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#a75e69';ctx.lineWidth=3;for(let j=0;j<5;j++){ctx.beginPath();ctx.moveTo(cx-55+j*24,cy-42);ctx.quadraticCurveTo(cx-25+j*20,cy+5,cx-48+j*25,cy+43);ctx.stroke()}glow(cx+20,cy,110,'#f7c3ad55')}
else if(/fingerprint|fingerprints/.test(sceneText+" "+topic)){ctx.strokeStyle='#f1d7a0';ctx.lineWidth=5;for(let j=0;j<8;j++){ctx.beginPath();ctx.ellipse(cx,cy,25+j*12,35+j*13,0,Math.PI*.12,Math.PI*1.88);ctx.stroke()}ctx.beginPath();ctx.arc(cx,cy+20,12,Math.PI,Math.PI*2);ctx.stroke()}
else if(/photosynth|plant|leaf|tree|seed|root|flower/.test(sceneText+" "+topic)){glow(cx,cy,140,'#d5e6a666');ctx.strokeStyle='#e8e0b1';ctx.lineWidth=6;ctx.beginPath();ctx.moveTo(cx,cy+115);ctx.lineTo(cx,cy-75);ctx.stroke();for(let j=0;j<6;j++){ctx.save();ctx.translate(cx,cy+60-j*24);ctx.rotate(j%2?-.6:.6);ctx.fillStyle=j%2?'#b9cb87':'#6c9d72';ctx.beginPath();ctx.ellipse(28,0,18,38,0,0,Math.PI*2);ctx.fill();ctx.restore()}glow(cx-65,cy-90,65,'#ffe9a077')}
else if(/space|planet|solar|moon|star|universe|gravity/.test(topic+" "+sceneText)){glow(cx,cy,180,'#fff0bd66');for(let i=0;i<28;i++){let x=(i*137+83)%c.width,y=(i*83+51)%(c.height*.68);ctx.fillStyle='#fff6d8';ctx.globalAlpha=.45+(i%4)*.13;ctx.beginPath();ctx.arc(x,y,1.5+i%3,0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;ctx.fillStyle='#e8a77c';ctx.beginPath();ctx.arc(cx,cy,72,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#f8dfac';ctx.lineWidth=3;ctx.beginPath();ctx.ellipse(cx,cy,132,35,-.28,0,Math.PI*2);ctx.stroke();glow(cx-24,cy-28,45,'#fff2bd88')}
else if(/atom|molecule|chem|electron|element/.test(topic+" "+sceneText)){glow(cx,cy,150,'#d7edc966');for(let j=0;j<3;j++){ctx.strokeStyle=['#f8e4ad','#d5e8c4','#f4bca0'][j];ctx.lineWidth=3;ctx.beginPath();ctx.ellipse(cx,cy,120,45,j*Math.PI/3,0,Math.PI*2);ctx.stroke()}ctx.fillStyle='#f6c38d';ctx.beginPath();ctx.arc(cx,cy,20,0,Math.PI*2);ctx.fill();for(let j=0;j<3;j++){let a=j*2.1;ctx.fillStyle='#eaf0c9';ctx.beginPath();ctx.arc(cx+120*Math.cos(a),cy+45*Math.sin(a),9,0,Math.PI*2);ctx.fill()}}
else if(/plant|leaf|photosynth|forest|tree|nature|ecosystem/.test(topic+" "+sceneText)){glow(cx,cy,140,'#d5e6a666');for(let j=0;j<7;j++){ctx.save();ctx.translate(cx,cy+65);ctx.rotate((j-3)*.23);ctx.fillStyle=j%2?'#b9cb87':'#6c9d72';ctx.beginPath();ctx.ellipse(0,-55-j*8,18,52,-.35,0,Math.PI*2);ctx.fill();ctx.restore()}line(cx,cy+100,cx,cy-100,'#e8e0b1',5)}
else if(/winter|snow|hibernate|migration|migrate|cold|frost|squirrel|bear|fox|bird/.test(topic+" "+sceneText)){
  for(let i=0;i<85;i++){let x=(i*173+41)%c.width,y=(i*97+19)%(c.height*.78);ctx.globalAlpha=.25+(i%5)*.1;ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x,y,1+(i%3),0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;
  const bear=/bear|hibernate|den|sleep|hibernat/.test(sceneText), bird=/bird|fly|migration|migrat|south|wing/.test(sceneText), squirrel=/squirrel|nut|food|store|cache/.test(sceneText);
  const ax=c.width*.69, ay=c.height*.61;
  if(bird){for(let k=0;k<5;k++){let bx=ax-145+k*58,by=ay-70-(k%2)*26;ctx.strokeStyle='#425d70';ctx.lineWidth=8;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(bx-20,by+8);ctx.quadraticCurveTo(bx,by-17,bx+17,by+8);ctx.quadraticCurveTo(bx+31,by-13,bx+43,by+1);ctx.stroke()}}
  else if(bear){ctx.fillStyle='#76594e';ctx.beginPath();ctx.ellipse(ax,ay,112,73,-.12,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(ax+65,ay-47,49,0,Math.PI*2);ctx.fill();ctx.fillStyle='#76594e';ctx.beginPath();ctx.arc(ax+34,ay-82,19,0,Math.PI*2);ctx.arc(ax+88,ay-82,18,0,Math.PI*2);ctx.fill();ctx.fillStyle='#f0d7bd';ctx.beginPath();ctx.ellipse(ax+84,ay-33,24,16,0,0,Math.PI*2);ctx.fill();ctx.fillStyle='#3b3b3b';ctx.beginPath();ctx.arc(ax+94,ay-42,5,0,Math.PI*2);ctx.fill()}
  else if(squirrel){ctx.fillStyle='#b8754f';ctx.beginPath();ctx.ellipse(ax,ay,48,60,-.2,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.ellipse(ax-40,ay-52,30,49,-.65,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(ax+4,ay-53,33,0,Math.PI*2);ctx.fill();ctx.fillStyle='#f3d4a5';ctx.beginPath();ctx.ellipse(ax+12,ay-43,20,15,0,0,Math.PI*2);ctx.fill();ctx.fillStyle='#342e2c';ctx.beginPath();ctx.arc(ax+14,ay-60,4,0,Math.PI*2);ctx.fill();ctx.fillStyle='#e9c58b';ctx.beginPath();ctx.ellipse(ax+36,ay-6,13,18,0,0,Math.PI*2);ctx.fill()}
  else {ctx.fillStyle='#bd855d';ctx.beginPath();ctx.ellipse(ax,ay,87,57,-.08,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(ax+62,ay-40,43,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.moveTo(ax+40,ay-72);ctx.lineTo(ax+47,ay-112);ctx.lineTo(ax+65,ay-78);ctx.fill();ctx.beginPath();ctx.moveTo(ax+70,ay-76);ctx.lineTo(ax+98,ay-105);ctx.lineTo(ax+91,ay-62);ctx.fill();ctx.fillStyle='#f3e1ca';ctx.beginPath();ctx.ellipse(ax+82,ay-28,24,13,.15,0,Math.PI*2);ctx.fill();ctx.fillStyle='#2e3030';ctx.beginPath();ctx.arc(ax+78,ay-49,4,0,Math.PI*2);ctx.fill()}
}
else {glow(cx,cy,145,'#fff0c866');ctx.strokeStyle='#f8e7bb';ctx.lineWidth=4;ctx.beginPath();ctx.arc(cx,cy,72,0,Math.PI*2);ctx.stroke();ctx.beginPath();ctx.arc(cx,cy,112,0,Math.PI*2);ctx.stroke();for(let j=0;j<8;j++){let a=j*Math.PI/4;line(cx+80*Math.cos(a),cy+80*Math.sin(a),cx+104*Math.cos(a),cy+104*Math.sin(a),'#f7d7a0',3)}}
</script></body></html>"""

def _safe(value: object) -> str:
    return html.escape(" ".join(str(value or "").split()), quote=True)

async def render_scenes(story: dict, output_dir: Path, width: int, height: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    scenes = story.get("scenes", [])
    rendered=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1)
        for i, scene in enumerate(scenes):
            title=_safe(scene.get("title") or story.get("topic") or "A Science Discovery")
            caption=_safe(scene.get("narration") or scene.get("visual_description") or "")
            topic=_safe(story.get("topic") or title)
            sceneText=_safe(title+" "+str(scene.get("visual") or scene.get("visual_description") or "")+" "+str(scene.get("narration") or ""))
            env_hint=str(scene.get("background") or "").lower()
            searchable=(topic+" "+sceneText+" "+env_hint).lower()
            if any(k in sceneText.lower() for k in ("magnet","magnetic","compass","pole","attract","repel","iron filing","field line")):
                sceneClass="magnet"
            elif any(k in searchable for k in ("winter","snow","hibernate","migration","migrate","cold","frost","squirrel","bear","fox","bird")):
                sceneClass="winter"
            else:
                env=next((name for name,words in {
                    "ocean":("ocean","sea","underwater","coral","whale","fish"),
                    "space":("space","planet","solar","moon","star","universe","gravity","black hole"),
                    "lab":("lab","laboratory","experiment","chemical","atom","molecule","electron"),
                    "desert":("desert","sand dune","arid"),
                    "city":("city","traffic","building","urban"),
                    "home":("home","house","bedroom","kitchen","indoors"),
                    "cave":("cave","den","underground"),
                    "mountain":("mountain","volcano","summit","glacier"),
                    "forest":("forest","tree","plant","leaf","bee","ecosystem"),
                }.items() if env_hint==name or any(word in searchable for word in words)), "")
                sceneClass=env
            html_doc=(PAGE.replace("WIDTH",str(width)).replace("HEIGHT",str(height))
                      .replace("TITLE",_safe(story.get("topic") or title)).replace("CAPTION",caption[:150])
                      .replace("INDEX",f"{i+1:02d} / {len(scenes):02d}")
                      .replace("SCENECLASS",sceneClass)
                      .replace("SCENENO",str(i+1))
                      .replace("TOPIC",json.dumps(topic))
                      .replace("SCENETEXT",json.dumps(sceneText)))
            await page.set_content(html_doc,wait_until="load")
            path=output_dir/f"scene-{i:03d}.png"
            await page.screenshot(path=str(path),type="png")
            rendered.append(path)
        await browser.close()
    return rendered

"""Render original storybook scenes with HTML/CSS and JavaScript; no image-generation API."""
from __future__ import annotations
import asyncio, json, html
from pathlib import Path
from playwright.async_api import async_playwright

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:WIDTHpx;height:HEIGHTpx;overflow:hidden}
.scene{position:relative;width:WIDTHpx;height:HEIGHTpx;overflow:hidden;background:linear-gradient(180deg,#7eb8d1 0%,#c6d9c6 48%,#f2c98e 100%);font-family:Georgia,serif;color:#fff7d9}.scene.winter{background:linear-gradient(180deg,#344d70 0%,#a7c7d5 55%,#e6edf0 100%)}.winter .sun{background:radial-gradient(circle at 35% 32%,#fff,#dcebf0 70%,#b5d2df);box-shadow:0 0 65px #e5f6ff88}.winter .mountain{background:#c2d5df}.winter .hill.back{background:linear-gradient(150deg,#e4edf0,#b7d0db)}.winter .hill{background:linear-gradient(160deg,#e9f0f2,#b7cbd5 80%)}.winter .field{background:linear-gradient(180deg,#f5f7f6,#d5e2e8)}.winter .tree:before{background:radial-gradient(circle at 36% 30%,#d9e8e7,#65828a 72%);box-shadow:35px 20px 0 -15px #78959d,-25px 30px 0 -20px #9bb8c0}.winter .tree:after{background:#c9dfe3}
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
.kicker{position:absolute;top:38px;left:52px;font:600 14px/1.2 system-ui,sans-serif;letter-spacing:3px;text-transform:uppercase;color:#fff4d2;text-shadow:0 2px 8px #263e38}
.title{position:absolute;left:52px;bottom:76px;width:75%;font-size:42px;line-height:1.08;font-weight:600;text-shadow:0 3px 14px #203b36}
.narration{position:absolute;left:54px;bottom:35px;width:72%;font:16px/1.35 system-ui,sans-serif;color:#fff7e6;text-shadow:0 2px 8px #203b36}
.index{position:absolute;right:48px;bottom:38px;font:13px system-ui,sans-serif;letter-spacing:2px}
#science{position:absolute;inset:0;width:100%;height:100%}
</style></head><body><main class="scene SCENECLASS"><div class="skyglow"></div><div class="sun"></div><div class="cloud"></div><div class="cloud c2"></div><div class="mountain"></div><div class="hill back"></div><div class="hill"></div><div class="field"></div><div class="tree t1"></div><div class="tree t2"></div><div class="tree t3"></div><canvas id="science"></canvas><div class="vignette"></div><div class="paper"></div><div class="kicker">A little science story</div><div class="title">TITLE</div><div class="narration">CAPTION</div><div class="index">INDEX</div></main><script>
const c=document.getElementById('science'),ctx=c.getContext('2d');c.width=WIDTH;c.height=HEIGHT;
const topic=TOPIC.toLowerCase(); const sceneText=SCENETEXT.toLowerCase(); const sceneNo=SCENENO; const cx=c.width*(.52+((sceneNo%4)*.055)), cy=c.height*(.39+((sceneNo%3)*.055));
function line(x1,y1,x2,y2,color='#fff1bd',w=3){ctx.strokeStyle=color;ctx.lineWidth=w;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()}
function glow(x,y,r,color){const g=ctx.createRadialGradient(x,y,2,x,y,r);g.addColorStop(0,color);g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()}
if(/space|planet|solar|moon|star|universe|gravity/.test(topic+" "+sceneText)){glow(cx,cy,180,'#fff0bd66');for(let i=0;i<28;i++){let x=(i*137+83)%c.width,y=(i*83+51)%(c.height*.68);ctx.fillStyle='#fff6d8';ctx.globalAlpha=.45+(i%4)*.13;ctx.beginPath();ctx.arc(x,y,1.5+i%3,0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;ctx.fillStyle='#e8a77c';ctx.beginPath();ctx.arc(cx,cy,72,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#f8dfac';ctx.lineWidth=3;ctx.beginPath();ctx.ellipse(cx,cy,132,35,-.28,0,Math.PI*2);ctx.stroke();glow(cx-24,cy-28,45,'#fff2bd88')}
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
            caption=_safe(scene.get("visual") or scene.get("visual_description") or scene.get("narration") or "")
            topic=_safe(story.get("topic") or title)
            sceneText=_safe(title+" "+str(scene.get("visual") or scene.get("visual_description") or "")+" "+str(scene.get("narration") or ""))
            sceneClass="winter" if any(k in (topic+" "+sceneText).lower() for k in ("winter","snow","hibernate","migration","migrate","cold","frost","squirrel","bear","fox","bird")) else ""
            html_doc=(PAGE.replace("WIDTH",str(width)).replace("HEIGHT",str(height))
                      .replace("TITLE",title).replace("CAPTION",caption[:210])
                      .replace("INDEX",f"{i+1:02d} / {len(scenes):02d}")
                      .replace("SCENECLASS",sceneClass)
                      .replace("TOPIC",json.dumps(topic))
                      .replace("SCENETEXT",json.dumps(sceneText)))
            await page.set_content(html_doc,wait_until="load")
            path=output_dir/f"scene-{i:03d}.png"
            await page.screenshot(path=str(path),type="png")
            rendered.append(path)
        await browser.close()
    return rendered

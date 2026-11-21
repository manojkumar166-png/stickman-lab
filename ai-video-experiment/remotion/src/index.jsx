import React from "react";
import {registerRoot} from "remotion";
import {AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, staticFile, useCurrentFrame} from "remotion";

const Scene = ({scene, index, duration, total}) => {
  const frame = useCurrentFrame();
  const progress = frame / Math.max(1, duration);
  const scale = interpolate(frame, [0, duration], [1.025, 1.13], {extrapolateRight: "clamp"});
  const drift = index % 2 === 0 ? -1 : 1;
  const fade = 12;
  const opacity = interpolate(
    frame,
    [0, fade, Math.max(fade + 1, duration - fade), duration],
    [0, 1, 1, 0],
    {extrapolateLeft: "clamp", extrapolateRight: "clamp"}
  );
  return (
    <AbsoluteFill style={{backgroundColor: "#080d18", overflow: "hidden"}}>
      <Img
        src={staticFile(scene.image)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translateX(${drift * progress * 1.5}%)`,
          filter: "saturate(1.06) contrast(1.04)"
        }}
      />
      <AbsoluteFill style={{
        background: "linear-gradient(90deg, rgba(3,8,18,.72), rgba(3,8,18,.12) 78%), linear-gradient(0deg, rgba(0,0,0,.48), transparent 52%)"
      }}/>
      <AbsoluteFill style={{justifyContent:"flex-end", padding:"0 76px 68px", opacity}}>
        <div style={{fontFamily:"Arial,sans-serif", color:"#9fe7ff", fontSize:20, fontWeight:700, letterSpacing:4, marginBottom:16}}>
          SCENE {String(index+1).padStart(2,"0")} / {String(total).padStart(2,"0")}
        </div>
        <div style={{fontFamily:"Arial,sans-serif", color:"#fff", fontSize:48, lineHeight:1.12, fontWeight:800, maxWidth:"84%", textShadow:"0 4px 24px rgba(0,0,0,.5)"}}>
          {scene.heading}
        </div>
        <div style={{height:5, width:96, background:"#72d7ff", marginTop:24, borderRadius:8}}/>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Video = ({scenes, audio, sceneDurations}) => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{background:"#080d18"}}>
      {scenes.map((scene,index)=>{
        const from = cursor;
        const duration = sceneDurations[index];
        cursor += duration;
        return (
          <Sequence key={scene.image} from={from} durationInFrames={duration}>
            <Scene scene={scene} index={index} duration={duration} total={scenes.length}/>
          </Sequence>
        );
      })}
      <Audio src={staticFile(audio)} />
    </AbsoluteFill>
  );
};

const Root = () => (
  <Composition
    id="AIExperiment"
    component={Video}
    width={1280}
    height={720}
    fps={24}
    durationInFrames={24}
    defaultProps={{scenes:[],audio:"narration.mp3",sceneDurations:[24]}}
    calculateMetadata={({props})=>({
      durationInFrames: Math.max(24, props.sceneDurations.reduce((sum, frames) => sum + frames, 0))
    })}
  />
);
registerRoot(Root);

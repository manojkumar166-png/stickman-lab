import React from "react";
import {AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from "remotion";

const FPS = 30;
const TRANSITION_FRAMES = 14;

const Scene = ({scene, index, duration}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const progress = Math.min(1, Math.max(0, frame / Math.max(1, duration)));
  const scale = interpolate(frame, [0, duration], [1.02, 1.13], {extrapolateRight: "clamp"});
  const drift = index % 2 === 0 ? -1 : 1;
  const opacity = interpolate(
    frame,
    [0, TRANSITION_FRAMES, Math.max(TRANSITION_FRAMES + 1, duration - TRANSITION_FRAMES), duration],
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
          transform: `scale(${scale}) translateX(${drift * progress * 1.2}%)`,
          filter: "saturate(1.06) contrast(1.04)"
        }}
      />
      <AbsoluteFill style={{background: "linear-gradient(90deg, rgba(3,8,18,.78) 0%, rgba(3,8,18,.30) 62%, rgba(3,8,18,.06) 100%), linear-gradient(0deg, rgba(0,0,0,.55), transparent 48%)"}} />
      <AbsoluteFill style={{justifyContent: "flex-end", padding: "0 86px 76px", opacity}}>
        <div style={{fontFamily: "Arial, sans-serif", color: "#9fe7ff", fontSize: 22, fontWeight: 700, letterSpacing: 5, textTransform: "uppercase", marginBottom: 18}}>
          {String(index + 1).padStart(2, "0")} / {scene.total}
        </div>
        <div style={{fontFamily: "Arial, sans-serif", color: "white", fontSize: 52, lineHeight: 1.12, fontWeight: 800, maxWidth: width * 0.78, textShadow: "0 4px 24px rgba(0,0,0,.45)"}}>
          {scene.heading}
        </div>
        <div style={{height: 5, width: 104, background: "#72d7ff", marginTop: 26, borderRadius: 8}} />
      </AbsoluteFill>
      <Audio src={staticFile(scene.audio)} />
    </AbsoluteFill>
  );
};

const Story = ({scenes}) => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{backgroundColor: "#080d18"}}>
      {scenes.map((scene, index) => {
        const from = cursor;
        cursor += scene.durationInFrames;
        return (
          <Sequence key={scene.scene_number} from={from} durationInFrames={scene.durationInFrames}>
            <Scene scene={{...scene, total: scenes.length}} index={index} duration={scene.durationInFrames} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const RemotionRoot = () => (
  <Composition
    id="AIStoryVideo"
    component={Story}
    width={1280}
    height={720}
    fps={FPS}
    durationInFrames={1}
    defaultProps={{scenes: []}}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(1, props.scenes.reduce((sum, scene) => sum + scene.durationInFrames, 0))
    })}
  />
);

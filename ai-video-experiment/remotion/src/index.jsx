import React from "react";
import {registerRoot} from "remotion";
import {AbsoluteFill, Audio, Composition, Img, Sequence, interpolate, staticFile, useCurrentFrame} from "remotion";

// Each scene is deliberately image-only: no scene numbers, headings, script text,
// title cards, gradients, or decorative overlays are placed over the generated art.
const Scene = ({scene, duration}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, duration], [1.025, 1.13], {
    extrapolateRight: "clamp"
  });

  return (
    <AbsoluteFill style={{backgroundColor: "#000000", overflow: "hidden"}}>
      <Img
        src={staticFile(scene.image)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale})`
        }}
      />
    </AbsoluteFill>
  );
};

const Video = ({scenes, audio, sceneDurations}) => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{background: "#000000"}}>
      {scenes.map((scene, index) => {
        const from = cursor;
        const duration = sceneDurations[index];
        cursor += duration;
        return (
          <Sequence key={scene.image} from={from} durationInFrames={duration}>
            <Scene scene={scene} duration={duration} />
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
    defaultProps={{scenes: [], audio: "narration.mp3", sceneDurations: [24]}}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(24, props.sceneDurations.reduce((sum, frames) => sum + frames, 0))
    })}
  />
);

registerRoot(Root);

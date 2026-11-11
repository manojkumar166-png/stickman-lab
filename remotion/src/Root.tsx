import React from "react";
import {Composition, getInputProps} from "remotion";
import {Explainer, ExplainerProps} from "./Video";

const fallbackProps: ExplainerProps = {
  topic: "A curious science explainer",
  scenes: [
    {title: "A surprising question", narration: "Every great discovery begins with a question. Let's explore the idea step by step.", action: "think"},
    {title: "Look closer", narration: "When we look closely, ordinary things can reveal patterns that are easy to miss.", action: "observe"}
  ],
  sceneDurations: [360, 360],
  audioFile: "narration.mp3",
  musicFile: "ambient.wav"
};

const supplied = getInputProps() as Partial<ExplainerProps>;
const initial = {...fallbackProps, ...supplied};
const totalFrames = Math.max(1, initial.sceneDurations.reduce((sum, value) => sum + value, 0));

export const Root: React.FC = () => (
  <Composition
    id="Main"
    component={Explainer}
    durationInFrames={totalFrames}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={initial}
    calculateMetadata={({props}) => ({
      durationInFrames: Math.max(1, props.sceneDurations.reduce((sum, value) => sum + value, 0))
    })}
  />
);

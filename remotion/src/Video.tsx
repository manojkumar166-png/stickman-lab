import React from "react";
import {
  AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig
} from "remotion";
import {ThreeCanvas} from "@remotion/three";

export type ExplainerScene = {
  title: string;
  narration: string;
  action?: string;
  visual?: string;
  background?: string;
};

export type ExplainerProps = {
  topic: string;
  scenes: ExplainerScene[];
  sceneDurations: number[];
  audioFile: string;
  musicFile?: string;
};

const palettes = [
  ["#071a2d", "#102f48", "#36c6d9"],
  ["#21143d", "#43245f", "#f4b942"],
  ["#102b25", "#1e5945", "#79d6a3"],
  ["#321b28", "#653448", "#ff8b75"],
  ["#18213c", "#2d4678", "#9ab8ff"]
];

const Character: React.FC<{frame: number; action: string}> = ({frame, action}) => {
  const wave = Math.sin(frame / 13) * 0.22;
  const run = action.toLowerCase().includes("run") || action.toLowerCase().includes("walk");
  const think = action.toLowerCase().includes("think") || action.toLowerCase().includes("observe");
  const armSwing = run ? Math.sin(frame / 5) * 0.65 : wave;
  return (
    <group position={[-1.15, -0.5, 0]} rotation={[0, Math.sin(frame / 70) * 0.12, 0]}>
      <mesh position={[0, 1.45, 0]}>
        <sphereGeometry args={[0.34, 32, 32]} />
        <meshStandardMaterial color="#ffd6ad" roughness={0.55} />
      </mesh>
      <mesh position={[0, 0.72, 0]}>
        <capsuleGeometry args={[0.19, 0.72, 8, 16]} />
        <meshStandardMaterial color="#f4f1eb" roughness={0.72} />
      </mesh>
      <mesh position={[-0.31, 0.82, 0]} rotation={[0, 0, -0.55 + armSwing]}>
        <capsuleGeometry args={[0.085, 0.68, 6, 12]} />
        <meshStandardMaterial color="#ffd6ad" />
      </mesh>
      <mesh position={[0.31, 0.82, 0]} rotation={[0, 0, 0.55 - (think ? 0.5 : armSwing)]}>
        <capsuleGeometry args={[0.085, 0.68, 6, 12]} />
        <meshStandardMaterial color="#ffd6ad" />
      </mesh>
      <mesh position={[-0.15, 0.02, 0]} rotation={[0, 0, 0.12 + (run ? armSwing : 0)]}>
        <capsuleGeometry args={[0.095, 0.72, 6, 12]} />
        <meshStandardMaterial color="#56a7d9" />
      </mesh>
      <mesh position={[0.15, 0.02, 0]} rotation={[0, 0, -0.12 - (run ? armSwing : 0)]}>
        <capsuleGeometry args={[0.095, 0.72, 6, 12]} />
        <meshStandardMaterial color="#56a7d9" />
      </mesh>
      <mesh position={[0, 1.47, 0.29]}>
        <sphereGeometry args={[0.035, 12, 12]} />
        <meshBasicMaterial color="#20202a" />
      </mesh>
      <mesh position={[0.13, 1.47, 0.29]}>
        <sphereGeometry args={[0.035, 12, 12]} />
        <meshBasicMaterial color="#20202a" />
      </mesh>
    </group>
  );
};

const SceneWorld: React.FC<{index: number; frame: number; action: string; visual: string}> = ({index, frame, action, visual}) => {
  const palette = palettes[index % palettes.length];
  const spin = frame * 0.012;
  const description = visual.toLowerCase();
  const kind = /money|coin|cash|dollar|wealth|salary|bank/.test(description) ? "coin"
    : /planet|earth|moon|space|orbit|star/.test(description) ? "planet"
    : /atom|molecule|chemical|science|cell/.test(description) ? "molecule"
    : /city|building|house|tower|office/.test(description) ? "building"
    : index % 4 === 0 ? "knot" : index % 4 === 1 ? "sphere" : index % 4 === 2 ? "crystal" : "ring";
  return (
    <ThreeCanvas width={1920} height={1080} camera={{fov: 42, position: [0, 0, 8.2]}} style={{background: palette[0]}}>
      <ambientLight intensity={0.72} />
      <directionalLight position={[4, 7, 6]} intensity={2.1} />
      <pointLight position={[-4, 2, 4]} intensity={1.2} color={palette[2]} />
      <mesh position={[0, -2.15, -1]}>
        <boxGeometry args={[14, 0.25, 3]} />
        <meshStandardMaterial color={palette[1]} roughness={0.9} />
      </mesh>
      <Character frame={frame} action={action} />
      <group position={[1.6, 0.35, -0.2]} rotation={[spin * 0.3, spin, spin * 0.2]}>
        {kind === "coin" ? (
          <mesh rotation={[Math.PI / 2.8, spin, 0]}>
            <cylinderGeometry args={[0.9, 0.9, 0.16, 64]} />
            <meshStandardMaterial color="#f4c34e" metalness={0.82} roughness={0.2} />
          </mesh>
        ) : kind === "planet" ? (
          <group>
            <mesh>
              <sphereGeometry args={[0.95, 48, 48]} />
              <meshStandardMaterial color="#4d9bd8" metalness={0.18} roughness={0.42} />
            </mesh>
            <mesh rotation={[0.8, 0.25, 0.2]}>
              <torusGeometry args={[1.35, 0.055, 16, 96]} />
              <meshStandardMaterial color={palette[2]} />
            </mesh>
          </group>
        ) : kind === "molecule" ? (
          <group>
            <mesh><sphereGeometry args={[0.38, 24, 24]} /><meshStandardMaterial color={palette[2]} /></mesh>
            <mesh position={[0.72, 0.35, 0]}><sphereGeometry args={[0.27, 20, 20]} /><meshStandardMaterial color="#f4b942" /></mesh>
            <mesh position={[-0.68, -0.38, 0]}><sphereGeometry args={[0.27, 20, 20]} /><meshStandardMaterial color="#e87b72" /></mesh>
            <mesh position={[0.08, 0.85, 0]}><sphereGeometry args={[0.22, 20, 20]} /><meshStandardMaterial color="#79d6a3" /></mesh>
            <mesh rotation={[0, 0, 0.4]}><torusGeometry args={[0.72, 0.045, 10, 48]} /><meshStandardMaterial color="#e7edf5" /></mesh>
          </group>
        ) : kind === "building" ? (
          <group>
            <mesh position={[-0.35, -0.15, 0]}><boxGeometry args={[0.65, 1.5, 0.55]} /><meshStandardMaterial color={palette[2]} /></mesh>
            <mesh position={[0.38, 0.1, -0.08]}><boxGeometry args={[0.58, 2.0, 0.5]} /><meshStandardMaterial color="#f4b942" /></mesh>
            <mesh position={[0.05, -0.9, 0.2]}><boxGeometry args={[1.35, 0.16, 0.75]} /><meshStandardMaterial color="#e7edf5" /></mesh>
          </group>
        ) : kind === "knot" ? (
          <mesh><torusKnotGeometry args={[0.92, 0.24, 140, 18]} /><meshStandardMaterial color={palette[2]} metalness={0.3} roughness={0.3} /></mesh>
        ) : kind === "sphere" ? (
          <mesh><sphereGeometry args={[1.05, 48, 48]} /><meshStandardMaterial color={palette[2]} metalness={0.28} roughness={0.26} /></mesh>
        ) : kind === "crystal" ? (
          <mesh><icosahedronGeometry args={[1.1, 1]} /><meshStandardMaterial color={palette[2]} metalness={0.35} roughness={0.32} /></mesh>
        ) : (
          <mesh><torusGeometry args={[0.85, 0.23, 24, 80]} /><meshStandardMaterial color={palette[2]} metalness={0.3} roughness={0.3} /></mesh>
        )}
      </group>
      {Array.from({length: 12}, (_, i) => {
        const angle = (i / 12) * Math.PI * 2 + frame * 0.003;
        const radius = 2.5 + Math.sin(frame / 28 + i) * 0.12;
        return (
          <mesh key={i} position={[Math.cos(angle) * radius, Math.sin(angle) * radius * 0.68, -0.8]}>
            <sphereGeometry args={[0.045 + (i % 3) * 0.018, 12, 12]} />
            <meshBasicMaterial color={palette[2]} />
          </mesh>
        );
      })}
    </ThreeCanvas>
  );
};

const Scene: React.FC<{scene: ExplainerScene; index: number; duration: number}> = ({scene, index, duration}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fade = Math.min(1, interpolate(frame, [0, 18, duration - 18, duration], [0, 1, 1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}));
  const rise = interpolate(frame, [0, 24], [55, 0], {extrapolateRight: "clamp"});
  const palette = palettes[index % palettes.length];
  return (
    <AbsoluteFill style={{opacity: fade, background: `linear-gradient(120deg, ${palette[0]}, ${palette[1]})`}}>
      <SceneWorld index={index} frame={frame} action={scene.action || "explain"} visual={scene.visual || scene.title} />
      <AbsoluteFill style={{justifyContent: "flex-end", padding: "0 110px 90px", background: "linear-gradient(0deg, rgba(0,0,0,.82), transparent 58%)"}}>
        <div style={{fontFamily: "Arial, sans-serif", color: "#ffffff", fontSize: 28, letterSpacing: 5, textTransform: "uppercase", opacity: 0.8, marginBottom: 18}}>
          {scene.title}
        </div>
        <div style={{fontFamily: "Arial, sans-serif", color: "#ffffff", fontWeight: 800, fontSize: 49, lineHeight: 1.2, maxWidth: 1640, transform: `translateY(${rise}px)`, textShadow: "0 3px 18px rgba(0,0,0,.55)"}}>
          {scene.narration}
        </div>
        <div style={{marginTop: 26, width: 180, height: 7, borderRadius: 10, background: palette[2]}} />
      </AbsoluteFill>
      <div style={{position: "absolute", top: 52, left: 72, color: "rgba(255,255,255,.62)", fontFamily: "Arial", fontSize: 22, letterSpacing: 3}}>
        {String(index + 1).padStart(2, "0")} / EXPLAINER
      </div>
    </AbsoluteFill>
  );
};

export const Explainer: React.FC<ExplainerProps> = ({topic, scenes, sceneDurations, audioFile, musicFile}) => {
  const total = sceneDurations.reduce((sum, value) => sum + value, 0);
  let cursor = 0;
  const items = scenes.map((scene, index) => {
    const from = cursor;
    const duration = Math.max(1, sceneDurations[index] || 300);
    cursor += duration;
    return {scene, index, from, duration};
  });
  return (
    <AbsoluteFill style={{backgroundColor: "#071a2d"}}>
      {items.map(({scene, index, from, duration}) => (
        <Sequence key={index} from={from} durationInFrames={duration} premountFor={0}>
          <Scene scene={scene} index={index} duration={duration} />
        </Sequence>
      ))}
      <div style={{position: "absolute", top: 52, right: 72, fontFamily: "Arial", color: "rgba(255,255,255,.75)", fontSize: 24, letterSpacing: 2}}>
        {topic.toUpperCase()}
      </div>
      <Audio src={staticFile(audioFile)} />
      {musicFile ? <Audio src={staticFile(musicFile)} volume={0.12} /> : null}
    </AbsoluteFill>
  );
};

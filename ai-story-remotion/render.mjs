import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {execFileSync} from "node:child_process";
import {bundle} from "@remotion/bundler";
import {selectComposition, renderMedia} from "@remotion/renderer";

const remotionDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(remotionDir, "..");
const publicDir = path.join(remotionDir, "public");
const assetsDir = path.join(publicDir, "story");
const outputRoot = path.join(root, "ai-story-video-output");

function durationSeconds(file) {
  const value = execFileSync("ffprobe", [
    "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file
  ], {encoding: "utf8"}).trim();
  const duration = Number(value);
  if (!Number.isFinite(duration) || duration <= 0) throw new Error(`Invalid audio duration for ${file}`);
  return duration;
}

function validMedia(file, requireVideo = false) {
  if (!fs.existsSync(file) || fs.statSync(file).size < 2048) return false;
  try {
    const streams = execFileSync("ffprobe", [
      "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", file
    ], {encoding: "utf8"}).trim().split(/\s+/);
    return streams.includes("audio") && (!requireVideo || streams.includes("video"));
  } catch {
    return false;
  }
}

const packages = fs.readdirSync(outputRoot, {withFileTypes: true})
  .filter((entry) => entry.isDirectory())
  .map((entry) => path.join(outputRoot, entry.name))
  .filter((dir) => fs.existsSync(path.join(dir, "story.json")))
  .sort()
  .reverse();

const packageDir = packages.find((dir) => {
  try {
    const story = JSON.parse(fs.readFileSync(path.join(dir, "story.json"), "utf8"));
    return story.completed !== true && Array.isArray(story.scenes) && story.scenes.length > 0;
  } catch { return false; }
});
if (!packageDir) throw new Error("No unfinished AI story package with scenes was found.");

const story = JSON.parse(fs.readFileSync(path.join(packageDir, "story.json"), "utf8"));
const publicStoryDir = path.join(assetsDir, "images");
const publicAudioDir = path.join(assetsDir, "audio");
fs.rmSync(assetsDir, {recursive: true, force: true});
fs.mkdirSync(publicStoryDir, {recursive: true});
fs.mkdirSync(publicAudioDir, {recursive: true});

const scenes = [];
for (const [index, scene] of story.scenes.entries()) {
  const number = Number(scene.scene_number || index + 1);
  const imageSource = path.join(packageDir, "images", `scene-${String(number).padStart(2, "0")}.png`);
  const audioSource = path.join(packageDir, "audio", `scene-${String(number).padStart(2, "0")}.mp3`);
  if (!fs.existsSync(imageSource)) throw new Error(`Missing scene image: ${imageSource}`);
  if (!validMedia(audioSource)) throw new Error(`Missing or invalid scene narration: ${audioSource}`);
  const imageName = `scene-${String(number).padStart(2, "0")}.png`;
  const audioName = `scene-${String(number).padStart(2, "0")}.mp3`;
  fs.copyFileSync(imageSource, path.join(publicStoryDir, imageName));
  fs.copyFileSync(audioSource, path.join(publicAudioDir, audioName));
  const seconds = durationSeconds(audioSource) + 0.18;
  scenes.push({
    scene_number: number,
    heading: String(scene.heading || `Scene ${number}`),
    image: `story/images/${imageName}`,
    audio: `story/audio/${audioName}`,
    durationInFrames: Math.max(30, Math.ceil(seconds * 30))
  });
}

console.log(`Rendering ${scenes.length} AI story scenes with Remotion (1280x720, 30fps).`);
const serveUrl = await bundle({
  entryPoint: path.join(remotionDir, "src", "index.jsx"),
  publicDir
});
const inputProps = {scenes};
const composition = await selectComposition({
  serveUrl,
  id: "AIStoryVideo",
  inputProps
});
const output = path.join(packageDir, "final-video.mp4");
const temporary = path.join(packageDir, "final-video.remotion-rendering.mp4");
fs.rmSync(temporary, {force: true});
await renderMedia({
  composition,
  serveUrl,
  codec: "h264",
  outputLocation: temporary,
  inputProps,
  pixelFormat: "yuv420p",
  crf: 20,
  concurrency: 2,
  onProgress: ({progress}) => {
    const percent = Math.round(progress * 100);
    if (percent % 10 === 0) console.log(`Remotion render progress: ${percent}%`);
  }
});
if (!validMedia(temporary, true)) {
  fs.rmSync(temporary, {force: true});
  throw new Error("Remotion output failed audio/video stream validation.");
}
fs.renameSync(temporary, output);
console.log(`Remotion render complete: ${output}`);

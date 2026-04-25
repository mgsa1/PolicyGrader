import React from "react";
import { AbsoluteFill, Sequence, Audio } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadJetBrains } from "@remotion/google-fonts/JetBrainsMono";
import { TitleScene } from "./scenes/TitleScene";
import { PainScene } from "./scenes/PainScene";
import { PipelineScene } from "./scenes/PipelineScene";
import { PopulationsScene } from "./scenes/PopulationsScene";
import { JudgeScene } from "./scenes/JudgeScene";
import { NumbersScene } from "./scenes/NumbersScene";
import { Topbar } from "./components/Topbar";
import { colors, fonts } from "./theme";

loadInter();
loadJetBrains();

export const HERO_FPS = 30;

const sec = (s: number) => Math.round(s * HERO_FPS);

const SCENE_PLAN = [
  { name: "title", start: 0, dur: 4 },
  { name: "pain", start: 4, dur: 6 },
  { name: "pipeline", start: 10, dur: 10 },
  { name: "populations", start: 20, dur: 8 },
  { name: "judge", start: 28, dur: 6 },
  { name: "numbers", start: 34, dur: 6 },
] as const;

export const HERO_DURATION_FRAMES = sec(40);

export const Hero: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        background: colors.bg,
        color: colors.ink,
        fontFamily: fonts.sans,
        fontFeatureSettings: '"tnum" 1, "ss01" 1',
      }}
    >
      <Topbar />

      <Sequence from={sec(SCENE_PLAN[0].start)} durationInFrames={sec(SCENE_PLAN[0].dur)}>
        <TitleScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[1].start)} durationInFrames={sec(SCENE_PLAN[1].dur)}>
        <PainScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[2].start)} durationInFrames={sec(SCENE_PLAN[2].dur)}>
        <PipelineScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[3].start)} durationInFrames={sec(SCENE_PLAN[3].dur)}>
        <PopulationsScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[4].start)} durationInFrames={sec(SCENE_PLAN[4].dur)}>
        <JudgeScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[5].start)} durationInFrames={sec(SCENE_PLAN[5].dur)}>
        <NumbersScene />
      </Sequence>
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, Composition } from "remotion";
import { Hero, HERO_DURATION_FRAMES, HERO_FPS } from "./Hero";
import { PipelineScene } from "./scenes/PipelineScene";
import { PipelineFlowScene } from "./scenes/PipelineFlowScene";
import { Topbar } from "./components/Topbar";
import { colors, fonts } from "./theme";

const stageStyle = {
  background: colors.bg,
  color: colors.ink,
  fontFamily: fonts.sans,
  fontFeatureSettings: '"tnum" 1, "ss01" 1',
} as const;

// Cards row only — bottom data-flow row falls below the 800-px canvas.
const PipelineCardsStandalone: React.FC = () => (
  <AbsoluteFill style={stageStyle}>
    <Topbar />
    <PipelineScene />
  </AbsoluteFill>
);

// Flow row only, with timing reset so it animates from frame 0.
const PipelineFlowStandalone: React.FC = () => (
  <AbsoluteFill style={stageStyle}>
    <PipelineFlowScene />
  </AbsoluteFill>
);

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="Hero"
        component={Hero}
        durationInFrames={HERO_DURATION_FRAMES}
        fps={HERO_FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="PipelineCards"
        component={PipelineCardsStandalone}
        durationInFrames={22 * HERO_FPS}
        fps={HERO_FPS}
        width={1920}
        height={800}
      />
      <Composition
        id="PipelineFlow"
        component={PipelineFlowStandalone}
        durationInFrames={10 * HERO_FPS}
        fps={HERO_FPS}
        width={1920}
        height={520}
      />
    </>
  );
};

import React from "react";
import { AbsoluteFill, Composition } from "remotion";
import { Hero, HERO_DURATION_FRAMES, HERO_FPS } from "./Hero";
import { PipelineScene } from "./scenes/PipelineScene";
import { Topbar } from "./components/Topbar";
import { colors, fonts } from "./theme";

const PipelineStandalone: React.FC = () => (
  <AbsoluteFill
    style={{
      background: colors.bg,
      color: colors.ink,
      fontFamily: fonts.sans,
      fontFeatureSettings: '"tnum" 1, "ss01" 1',
    }}
  >
    <Topbar />
    <PipelineScene />
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
        id="Pipeline"
        component={PipelineStandalone}
        durationInFrames={22 * HERO_FPS}
        fps={HERO_FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};

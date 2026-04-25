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

// Cards row only — translate the scene up so its title/header fall above
// the canvas, leaving just SIM/AI stack brackets + 5 phase cards. The README
// already carries the tagline above the GIF, so the in-scene title is dead
// real estate for the hero.
const PipelineCardsStandalone: React.FC = () => (
  <AbsoluteFill style={stageStyle}>
    <AbsoluteFill style={{ transform: "translateY(-280px)" }}>
      <PipelineScene />
    </AbsoluteFill>
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
        height={370}
      />
      <Composition
        id="PipelineFlow"
        component={PipelineFlowStandalone}
        durationInFrames={10 * HERO_FPS}
        fps={HERO_FPS}
        width={1920}
        height={430}
      />
    </>
  );
};

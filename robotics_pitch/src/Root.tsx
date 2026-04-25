import React from "react";
import { Composition } from "remotion";
import { Hero, HERO_DURATION_FRAMES, HERO_FPS } from "./Hero";

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
    </>
  );
};

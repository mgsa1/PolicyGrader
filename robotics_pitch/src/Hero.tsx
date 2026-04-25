import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadJetBrains } from "@remotion/google-fonts/JetBrainsMono";
import { MarathonHookScene } from "./scenes/MarathonHookScene";
import { PersonalBeatScene } from "./scenes/PersonalBeatScene";
import { NameRevealScene } from "./scenes/NameRevealScene";
import { PipelineScene } from "./scenes/PipelineScene";
import { JudgeScene } from "./scenes/JudgeScene";
import { PopulationsScene } from "./scenes/PopulationsScene";
import { JudgeTrustScene } from "./scenes/JudgeTrustScene";
import { OpusMontageScene } from "./scenes/OpusMontageScene";
import { CloseScene } from "./scenes/CloseScene";
import { Topbar } from "./components/Topbar";
import { FaceSafeZone } from "./components/FaceSafeZone";
import { colors, fonts } from "./theme";

loadInter();
loadJetBrains();

export const HERO_FPS = 30;

const sec = (s: number) => Math.round(s * HERO_FPS);

// 2:30 submission cut. Each beat maps 1:1 to a section of Video.txt.
// Face-overlay corner: the user PiPs themselves at recording time.
// Scenes flagged `faceCam` keep a 360x360 px face-safe zone clear in the
// `faceSafeCorner` corner. See `FaceSafeZone` for the debug overlay.
const SCENE_PLAN = [
  { name: "marathon", start: 0, dur: 18, faceCam: false },
  { name: "personal", start: 18, dur: 15, faceCam: true, faceSafeCorner: "br" as const },
  { name: "nameReveal", start: 33, dur: 15, faceCam: true, faceSafeCorner: "br" as const },
  { name: "pipeline", start: 48, dur: 22, faceCam: true, faceSafeCorner: "br" as const },
  { name: "judgeDemo", start: 70, dur: 15, faceCam: false },
  { name: "populations", start: 85, dur: 15, faceCam: false },
  { name: "judgeTrust", start: 100, dur: 15, faceCam: false },
  { name: "opus", start: 115, dur: 25, faceCam: true, faceSafeCorner: "br" as const },
  { name: "close", start: 140, dur: 10, faceCam: false },
] as const;

export const HERO_DURATION_FRAMES = sec(150);

// Toggle to render face-safe-zone debug rectangles. Off for production renders.
const SHOW_FACE_SAFE_DEBUG = false;

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
      {/* Music bed + VO go here once recorded. Keep both at root so they
          play across all scenes. Example:
          <Audio src={staticFile("audio/music_bed.mp3")} volume={0.18} />
          <Audio src={staticFile("audio/vo.mp3")} />                       */}

      <Topbar />

      <Sequence from={sec(SCENE_PLAN[0].start)} durationInFrames={sec(SCENE_PLAN[0].dur)}>
        <MarathonHookScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[1].start)} durationInFrames={sec(SCENE_PLAN[1].dur)}>
        <PersonalBeatScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[2].start)} durationInFrames={sec(SCENE_PLAN[2].dur)}>
        <NameRevealScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[3].start)} durationInFrames={sec(SCENE_PLAN[3].dur)}>
        <PipelineScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[4].start)} durationInFrames={sec(SCENE_PLAN[4].dur)}>
        <JudgeScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[5].start)} durationInFrames={sec(SCENE_PLAN[5].dur)}>
        <PopulationsScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[6].start)} durationInFrames={sec(SCENE_PLAN[6].dur)}>
        <JudgeTrustScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[7].start)} durationInFrames={sec(SCENE_PLAN[7].dur)}>
        <OpusMontageScene />
      </Sequence>
      <Sequence from={sec(SCENE_PLAN[8].start)} durationInFrames={sec(SCENE_PLAN[8].dur)}>
        <CloseScene />
      </Sequence>

      {SHOW_FACE_SAFE_DEBUG ? (
        <>
          {SCENE_PLAN.filter((s) => s.faceCam).map((s) => (
            <Sequence
              key={s.name}
              from={sec(s.start)}
              durationInFrames={sec(s.dur)}
            >
              <FaceSafeZone corner={s.faceSafeCorner ?? "br"} />
            </Sequence>
          ))}
        </>
      ) : null}
    </AbsoluteFill>
  );
};

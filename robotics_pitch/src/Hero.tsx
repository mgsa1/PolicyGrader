import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadJetBrains } from "@remotion/google-fonts/JetBrainsMono";
import { MarathonHookScene } from "./scenes/MarathonHookScene";
import { PersonalBeatScene } from "./scenes/PersonalBeatScene";
import { NameRevealScene } from "./scenes/NameRevealScene";
import { PipelineScene } from "./scenes/PipelineScene";
import { JudgeAnalysisScene } from "./scenes/JudgeAnalysisScene";
import { PopulationsScene } from "./scenes/PopulationsScene";
import { JudgeChallengesScene } from "./scenes/JudgeChallengesScene";
import { OpusMontageScene } from "./scenes/OpusMontageScene";
import { CloseScene } from "./scenes/CloseScene";
import { RatApiScene } from "./scenes/RatApiScene";
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
// `name` is the label shown in the Remotion Studio timeline — keep it
// short and ordered so scenes are easy to refer to in conversation.
const SCENE_PLAN = [
  { name: "01 · Marathon hook", start: 0, dur: 50, faceCam: false, Component: MarathonHookScene },
  { name: "02 · Personal beat", start: 50, dur: 15, faceCam: true, faceSafeCorner: "br" as const, Component: PersonalBeatScene },
  { name: "03 · Name reveal", start: 65, dur: 15, faceCam: true, faceSafeCorner: "br" as const, Component: NameRevealScene },
  { name: "04 · Pipeline", start: 80, dur: 22, faceCam: true, faceSafeCorner: "br" as const, Component: PipelineScene },
  // Visual evaluation: failed video left, judge analysis right. Final 7 s of
  // the scene cross-fade into a thumbnail + cluster cards reveal — the prior
  // JudgeTrustScene's deployment findings were folded into this beat.
  { name: "05 · Judge analysis", start: 102, dur: 22, faceCam: false, Component: JudgeAnalysisScene },
  // Engineering-challenge beat: point-abstention + telemetry-as-context,
  // with a 4×2 wall of buggy-dot keyframes between the bug and the fix.
  { name: "06 · Judge challenges", start: 124, dur: 16, faceCam: false, Component: JudgeChallengesScene },
  { name: "07 · Populations", start: 140, dur: 12, faceCam: false, Component: PopulationsScene },
  { name: "08 · Opus 4.7", start: 152, dur: 15, faceCam: true, faceSafeCorner: "br" as const, Component: OpusMontageScene },
  // Close holds ~5 s on the final card before the API_RAT post-credits, so
  // the headline numbers have time to land for VO.
  { name: "09 · Close", start: 167, dur: 15, faceCam: false, Component: CloseScene },
  // Post-credits sign-off referencing the user's side project, API_RAT.
  // The marathon hook is intentionally long (~30 s held pose on the
  // fully-resolved trip frame for VO room); user is reworking total length
  // separately.
  { name: "10 · API_RAT", start: 182, dur: 11, faceCam: false, Component: RatApiScene },
] as const;

export const HERO_DURATION_FRAMES = sec(193);

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

      {SCENE_PLAN.map(({ name, start, dur, Component }) => (
        <Sequence
          key={name}
          name={name}
          from={sec(start)}
          durationInFrames={sec(dur)}
        >
          <Component />
        </Sequence>
      ))}

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

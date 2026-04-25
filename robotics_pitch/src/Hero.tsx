import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
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
import { FaceCam } from "./components/FaceCam";
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
  { name: "01 · Marathon hook", start: 0, dur: 29, faceCam: false, Component: MarathonHookScene },
  { name: "02 · Personal beat", start: 29, dur: 8, faceCam: true, faceSafeCorner: "tr" as const, Component: PersonalBeatScene },
  { name: "03 · Name reveal", start: 37, dur: 17.5, faceCam: true, faceSafeCorner: "tr" as const, Component: NameRevealScene },
  { name: "04 · Pipeline", start: 54.5, dur: 40, faceCam: true, faceSafeCorner: "tr" as const, Component: PipelineScene },
  // Visual evaluation: failed video left, judge analysis right. Final 7 s of
  // the scene cross-fade into a thumbnail + cluster cards reveal — the prior
  // JudgeTrustScene's deployment findings were folded into this beat.
  { name: "05 · Judge analysis", start: 94.5, dur: 25, faceCam: true, faceSafeCorner: "tr" as const, Component: JudgeAnalysisScene },
  // Engineering-challenge beat: point-abstention + telemetry-as-context,
  // with a 4×2 wall of buggy-dot keyframes between the bug and the fix.
  { name: "06 · Judge challenges", start: 119.5, dur: 16, faceCam: true, faceSafeCorner: "tr" as const, Component: JudgeChallengesScene },
  { name: "07 · Populations", start: 135.5, dur: 10, faceCam: true, faceSafeCorner: "tr" as const, Component: PopulationsScene },
  { name: "08 · Opus 4.7", start: 145.5, dur: 14.8, faceCam: true, faceSafeCorner: "tr" as const, Component: OpusMontageScene },
  // Close holds ~5 s on the final card before the API_RAT post-credits, so
  // the headline numbers have time to land for VO.
  // Close = recording (~5.12 s) + 4 s of held final-card silence so the
  // headline numbers land for VO before API_RAT.
  { name: "09 · Close", start: 160.3, dur: 9.2, faceCam: true, faceSafeCorner: "tr" as const, Component: CloseScene },
  // Post-credits sign-off referencing the user's side project, API_RAT.
  // Trimmed from 11 s to 10.5 s so the composition cuts at the 3:00 cap.
  { name: "10 · API_RAT", start: 169.5, dur: 10.5, faceCam: true, faceSafeCorner: "tr" as const, Component: RatApiScene },
] as const;

// Hard cap at 3:00 (2:59:59 target). The hackathon submission limit.
export const HERO_DURATION_FRAMES = sec(180);

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
      {/* Hi-tech-corporate bed under everything. Track is ~2:53; the 3:00
          composition gets ~7 s of silence at the tail, which falls inside
          the held final-card pause before API_RAT. */}
      <Audio src={staticFile("audio/music_bed.mp3")} volume={0.015} />

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

      {/* Face cam + primary audio for scenes 01-03. Sequence duration is
          set to the full .mov length (~56.5 s) so the whole recording plays
          through, even if it bleeds ~2 s past the scene-03 boundary. */}
      <Sequence from={0} durationInFrames={sec(56.6)} layout="none">
        <FaceCam corner="tr" shape="circle" volume={1} />
      </Sequence>

      {/* Face cam + primary audio for scene 04 (Pipeline). Sequence duration
          matches the full .mov length (~43.3 s) so the whole recording plays
          through, even past the 40 s scene window. */}
      <Sequence from={sec(54.5)} durationInFrames={sec(43.3)} layout="none">
        <FaceCam
          src="webcam/sequence4.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for scene 05 (Judge analysis). Sequence
          duration matches the full .mov length (~27 s) so the whole
          recording plays through, even past the 25 s scene window. */}
      <Sequence from={sec(94.5)} durationInFrames={sec(27)} layout="none">
        <FaceCam
          src="webcam/sequence5.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for scene 06 (Judge challenges). Recording
          is ~15.5 s and the scene window is 16 s — recording fits inside the
          scene, no overflow. */}
      <Sequence from={sec(119.5)} durationInFrames={sec(15.5)} layout="none">
        <FaceCam
          src="webcam/sequence6.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for scene 07 (Populations). Scene window
          was reduced from 12 s to 10 s to match the recording exactly. */}
      <Sequence from={sec(135.5)} durationInFrames={sec(10)} layout="none">
        <FaceCam
          src="webcam/sequence7.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for scene 08 (Opus 4.7). Scene window was
          reduced from 15 s to 14.8 s to match the recording (~14.77 s). */}
      <Sequence from={sec(145.5)} durationInFrames={sec(14.8)} layout="none">
        <FaceCam
          src="webcam/sequence8.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for scene 09 (Close). Scene window was
          reduced from 15 s to 5.2 s to match the recording (~5.12 s). */}
      <Sequence from={sec(160.3)} durationInFrames={sec(5.2)} layout="none">
        <FaceCam
          src="webcam/sequence9.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
      </Sequence>

      {/* Face cam + primary audio for the API_RAT post-credits, starting
          right where sequence9.mov ends. Recording is ~9.33 s; it carries
          across the boundary between scene 09's pause and scene 10. */}
      <Sequence from={sec(165.5)} durationInFrames={sec(9.33)} layout="none">
        <FaceCam
          src="webcam/sequenceRAT.mov"
          corner="tr"
          shape="circle"
          volume={1}
        />
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

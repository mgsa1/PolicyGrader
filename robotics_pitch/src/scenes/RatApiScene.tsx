import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  OffthreadVideo,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 2:30–2:39 · Personal sign-off, post-credits.
//
// One 9 s scripted MuJoCo flythrough plays underneath: the camera dollies
// from a close-up of the cheese (with the ANTHROPIC_API_KEY label floating
// above) over to the Franka Panda victoriously shaking a broom, then arcs
// out and lands behind the rat. Per-beat overlay copy and a final sign-off
// card sit on top, cross-faded with the staged-fade vocabulary used by
// the rest of the timeline.
//
// The flythrough is rendered headless by API_RAT/render_pitch_video.py
// (drop in robotics_pitch/public/api_rat/flythrough.mp4) so the in-browser
// preview has no MuJoCo dependency.

// Beat boundaries, in frames (30 fps). The underlying flythrough is 9 s
// (270 f) of camera motion; the scene itself runs 11 s so the final card
// holds for ~2 s after fade-in (the video sits on its last frame). These
// boundaries match the camera-act boundaries inside render_pitch_video.py
// — when the camera arrives on the robot, the "the threat" overlay fades in.
const T_BEAT_2 = 81; // ~2.7 s — camera arriving on the Franka
const T_BEAT_3 = 195; // ~6.5 s — camera arcing out toward the rat

// Cross-fade overlap between overlay copy.
const FADE = 14;

// Final card revealed in the last ~1 s, after the camera lands on the rat.
const T_CARD = 240;

// Obviously-fake stand-in for a real key. CLAUDE.md §15 forbids displaying
// anything that could be mistaken for a live Anthropic credential.
const FAKE_KEY = "sk-ant-api03-***-DEMO";

// Final-card link is left as a placeholder — the project doesn't have a
// public URL yet and we don't invent one.
const RAT_API_URL = "TODO_URL";

export const RatApiScene: React.FC = () => {
  const frame = useCurrentFrame();

  // Three overlay-opacity envelopes, timed against the camera acts inside
  // the underlying flythrough video. The video itself never fades.
  const overlay1Op = interpolate(
    frame,
    [0, FADE, T_BEAT_2 - FADE, T_BEAT_2],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  const overlay2Op = interpolate(
    frame,
    [T_BEAT_2 - FADE, T_BEAT_2, T_BEAT_3 - FADE, T_BEAT_3],
    [0, 1, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  const overlay3Op = interpolate(
    frame,
    [T_BEAT_3 - FADE, T_BEAT_3],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  // Vignette + final card share the same fade-in. The vignette gives the
  // white sign-off text something to land on without washing out the rat
  // reveal underneath.
  const cardOp = useFadeIn(frame, T_CARD, 16);

  return (
    <AbsoluteFill style={{ background: "#000", overflow: "hidden" }}>
      {/* Underlying flythrough — one continuous take */}
      <OffthreadVideo
        src={staticFile("api_rat/flythrough.mp4")}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
        muted
      />

      {/* Per-beat overlay copy (eyebrow + chip), top-left corner so the
          camera subject in the lower / center frame stays unobscured. */}
      <Overlay
        opacity={overlay1Op}
        eyebrow="The prize"
        eyebrowColor={colors.cal}
        title="ANTHROPIC_API_KEY"
        chip={<KeyChip />}
      />
      <Overlay
        opacity={overlay2Op}
        eyebrow="The threat"
        eyebrowColor={colors.dep}
        title="Franka with a broom"
        chip={<ThreatChip />}
      />
      <Overlay
        opacity={overlay3Op}
        eyebrow="The player"
        eyebrowColor={colors.ink}
        title="One determined rat"
        chip={null}
      />

      {/* Soft dark gradient under the final card so the white text reads. */}
      <AbsoluteFill
        style={{
          opacity: cardOp,
          background:
            "linear-gradient(180deg, rgba(15,18,24,0.0) 35%, rgba(15,18,24,0.78) 100%)",
          pointerEvents: "none",
        }}
      />

      <FinalCard opacity={cardOp} url={RAT_API_URL} />
    </AbsoluteFill>
  );
};

// Eyebrow + title in a translucent card pinned to the top-left so it
// doesn't fight the underlying camera move for the eye.
const Overlay: React.FC<{
  opacity: number;
  eyebrow: string;
  eyebrowColor: string;
  title: string;
  chip: React.ReactNode;
}> = ({ opacity, eyebrow, eyebrowColor, title, chip }) => {
  return (
    <div
      style={{
        position: "absolute",
        top: 132,
        left: 96,
        opacity,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          letterSpacing: 2.6,
          color: eyebrowColor,
          textTransform: "uppercase",
          fontWeight: 600,
          background: "rgba(255,255,255,0.92)",
          padding: "6px 12px",
          borderRadius: 999,
          alignSelf: "flex-start",
        }}
      >
        ● {eyebrow}
      </div>
      <div
        style={{
          fontFamily: fonts.sans,
          fontSize: 52,
          fontWeight: 700,
          letterSpacing: -1.0,
          lineHeight: 1.0,
          color: "#fff",
          textShadow: "0 2px 18px rgba(0,0,0,0.55)",
        }}
      >
        {title}
      </div>
      {chip ? <div style={{ marginTop: 6 }}>{chip}</div> : null}
    </div>
  );
};

const KeyChip: React.FC = () => (
  <div
    style={{
      fontFamily: fonts.mono,
      fontSize: 14,
      padding: "8px 14px",
      borderRadius: 8,
      background: "rgba(15,18,24,0.78)",
      color: "#fef1d8",
      letterSpacing: 1.0,
      fontWeight: 600,
      border: `1px solid ${colors.calLine}`,
      display: "inline-block",
    }}
  >
    {FAKE_KEY}
  </div>
);

const ThreatChip: React.FC = () => (
  <div
    style={{
      fontFamily: fonts.mono,
      fontSize: 14,
      padding: "8px 14px",
      borderRadius: 8,
      background: "rgba(15,18,24,0.78)",
      color: colors.depSoft,
      letterSpacing: 1.0,
      fontWeight: 600,
      border: `1px solid ${colors.depLine}`,
      display: "inline-block",
    }}
  >
    while_alive(): broom.swing()
  </div>
);

const FinalCard: React.FC<{ opacity: number; url: string }> = ({ opacity, url }) => {
  return (
    <AbsoluteFill
      style={{
        opacity,
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 96,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          letterSpacing: 2.8,
          color: "rgba(255,255,255,0.72)",
          textTransform: "uppercase",
          marginBottom: 12,
        }}
      >
        Also by Matthieu Gallet
      </div>
      <div
        style={{
          fontFamily: fonts.sans,
          fontSize: 64,
          fontWeight: 700,
          letterSpacing: -1.6,
          color: "#fff",
          lineHeight: 1.0,
          textAlign: "center",
        }}
      >
        Rat API
      </div>
      <div
        style={{
          fontFamily: fonts.sans,
          fontSize: 22,
          color: "rgba(255,255,255,0.85)",
          letterSpacing: -0.2,
          marginTop: 14,
          textAlign: "center",
        }}
      >
        a game about stealing API keys
      </div>
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 14,
          color: "rgba(255,255,255,0.6)",
          letterSpacing: 1.4,
          marginTop: 18,
        }}
      >
        ↳ {url}
      </div>
    </AbsoluteFill>
  );
};

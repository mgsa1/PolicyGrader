import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  Img,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// Beijing humanoid marathon hook. Full scene runs ~50 s.
//
// The reveal chain (forward play → Q1 → rewind → trip freeze → red
// circle → Q2a/b/c) front-loads into the first ~20 s; the remaining
// ~30 s is a long pause on the fully-composed final state (trip frame +
// pulsing red circle + all questions visible) so VO has room to breathe.
//
// Beat 1 (0–6 s):  video plays forward 1.0 s → 7.0 s of source at native
//                  speed — robot walks up to the obstacle, trips, and
//                  collapses on the ground. No overlay yet.
// Beat 2 (6–12 s): freeze on the collapse frame. After ~1 s of silent
//                  hold, "What went wrong?" fades in (Q1) and holds for
//                  ~5 s before the rewind kicks.
// Beat 3 (12–13.5 s): video rewinds (1.5 s @ 1× speed, pre-encoded
//                  reverse clip) — the collapse undoes itself back to the
//                  moment of the trip.
// Beat 4 (13.5–20 s): freeze on the trip frame. Red circle pulses in at
//                  the foot. Q2 subtext lands in three staged lines.
// Beat 5 (20–50 s): long held pause on the fully-resolved composition —
//                  trip frame, red circle, Q1 (dimmed) + Q2a/b/c all
//                  visible. This is the VO-room pause.

// ============== TUNE HERE ================================================
// Coordinates of the foot the red dot should highlight (0..1 of clip box).
// Set CALIBRATE = true to overlay a coordinate grid in Studio for tuning.
const FOOT_X = 0.41;
const FOOT_Y = 0.77;
const CALIBRATE = false;
// =========================================================================

// Beat boundaries in scene-frames @ 30 fps.
const T_PLAY_END = 6 * 30; // forward video ends, freeze on collapse begins
const T_Q1_AT = T_PLAY_END + 30; // 1 s of silent collapse hold, then Q1 fades in
const T_REWIND_START = 12 * 30; // ~5 s of Q1 hold, then rewind — long pause moved to AFTER the full reveal
const T_REWIND_END = T_REWIND_START + Math.round(1.5 * 30); // 1.5 s reverse @ 1×
// Q2 has three staged lines, anchored after the rewind so they land on
// the trip-frame freeze with the red circle pulsing in. Apparition timers
// are slowed ~20% vs. the original pacing for VO breathing room.
const T_Q2A_AT = T_REWIND_END + 36; // "Figuring that / why it fails…"
const T_Q2B_AT = T_Q2A_AT + Math.round(2.88 * 30); // delayed: "millions of times"
const T_Q2C_AT = T_Q2B_AT + Math.round(2.4 * 30); // delayed: bridge to robotics audience

// Source-clip ranges (30 fps).
const FWD_START_FROM = 1 * 30; // start at 1.0 s
const FWD_END_AT = 7 * 30; // end at 7.0 s — collapse complete

export const MarathonHookScene: React.FC = () => {
  const frame = useCurrentFrame();

  // --- Red circle (trip moment) -------------------------------------------
  const circlePulseScale = interpolate(
    frame,
    [T_REWIND_END - 6, T_REWIND_END + 2, T_REWIND_END + 6],
    [2.4, 1.0, 1.0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  const circleOp = interpolate(
    frame,
    [T_REWIND_END - 6, T_REWIND_END + 4],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // --- Q1 ("What went wrong?") --------------------------------------------
  const q1Op = useFadeIn(frame, T_Q1_AT, 22);
  const q1Y = interpolate(frame, [T_Q1_AT, T_Q1_AT + 28], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  // Q1 dims slightly when Q2 enters but stays on screen.
  const q1Fade = interpolate(frame, [T_Q2A_AT - 4, T_Q2A_AT + 18], [1, 0.45], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // --- Q2a ("Figuring it fails / requires judgement") --------------------
  const q2aOp = useFadeIn(frame, T_Q2A_AT, 22);
  const q2aY = interpolate(frame, [T_Q2A_AT, T_Q2A_AT + 28], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // --- Q2b ("Now try doing it millions of times") — delayed --------------
  const q2bOp = useFadeIn(frame, T_Q2B_AT, 22);
  const q2bY = interpolate(frame, [T_Q2B_AT, T_Q2B_AT + 28], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // --- Q2c (audience bridge) — further delayed ---------------------------
  const q2cOp = useFadeIn(frame, T_Q2C_AT, 22);
  const q2cY = interpolate(frame, [T_Q2C_AT, T_Q2C_AT + 28], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  return (
    <AbsoluteFill
      style={{
        paddingTop: 132,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: 56,
      }}
    >
      {/* LEFT: video card */}
      <div
        style={{
          flex: 1,
          display: "grid",
          placeItems: "center",
        }}
      >
        <div
          style={{
            position: "relative",
            width: 720,
            height: 768,
            borderRadius: 22,
            overflow: "hidden",
            background: "#000",
            boxShadow:
              "0 28px 70px rgba(31,31,31,0.18), 0 0 0 1px rgba(31,31,31,0.08)",
          }}
        >
          {/* Beat 1: forward play 1.0 s → 7.0 s of source. */}
          <Sequence from={0} durationInFrames={T_PLAY_END}>
            <OffthreadVideo
              src={staticFile("marathon.mp4")}
              startFrom={FWD_START_FROM}
              endAt={FWD_END_AT}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              muted
            />
          </Sequence>

          {/* Beat 2: freeze on collapse still. */}
          <Sequence
            from={T_PLAY_END}
            durationInFrames={T_REWIND_START - T_PLAY_END}
          >
            <Img
              src={staticFile("marathon_collapse.jpg")}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </Sequence>

          {/* Beat 3: reversed clip plays — collapse → trip. */}
          <Sequence
            from={T_REWIND_START}
            durationInFrames={T_REWIND_END - T_REWIND_START}
          >
            <OffthreadVideo
              src={staticFile("marathon_rewind.mp4")}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              muted
            />
          </Sequence>

          {/* Beat 4: freeze on trip frame for the rest of the scene. */}
          <Sequence from={T_REWIND_END}>
            <Img
              src={staticFile("marathon_trip.jpg")}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </Sequence>

          {/* Red circle annotation — only after the rewind lands on the trip. */}
          <div
            style={{
              position: "absolute",
              left: `${FOOT_X * 100}%`,
              top: `${FOOT_Y * 100}%`,
              width: 100,
              height: 100,
              marginLeft: -50,
              marginTop: -50,
              borderRadius: 999,
              border: `4px solid ${colors.err}`,
              boxShadow: `0 0 0 1px rgba(255,255,255,0.4) inset, 0 0 30px ${colors.err}`,
              transform: `scale(${circlePulseScale})`,
              opacity: circleOp,
              pointerEvents: "none",
            }}
          />

          {/* Calibration overlay — set CALIBRATE=true to position the dot. */}
          {CALIBRATE ? <CalibrationGrid x={FOOT_X} y={FOOT_Y} /> : null}
        </div>
      </div>

      {/* RIGHT: text overlay */}
      <div
        style={{
          flex: 0.95,
          display: "flex",
          flexDirection: "column",
          gap: 32,
          paddingRight: 24,
        }}
      >
        {/* Q1: "What went wrong?" — appears over the collapse pause */}
        <div
          style={{
            opacity: q1Op * q1Fade,
            transform: `translateY(${q1Y}px)`,
            fontSize: 88,
            fontWeight: 700,
            lineHeight: 1.0,
            letterSpacing: -2.4,
            color: colors.ink,
          }}
        >
          What went{" "}
          <span style={{ color: colors.err }}>wrong</span>?
        </div>

        {/* Q2a: appears after the rewind to the trip frame */}
        <div
          style={{
            opacity: q2aOp,
            transform: `translateY(${q2aY}px)`,
            fontSize: 38,
            fontWeight: 500,
            lineHeight: 1.25,
            letterSpacing: -0.6,
            color: colors.ink2,
            maxWidth: 720,
          }}
        >
          Figuring{" "}
          <span style={{ color: colors.ink3 }}>that</span> it fails is easy.
          <br />
          Figuring{" "}
          <span style={{ color: colors.ink3 }}>why</span> it fails requires{" "}
          <span style={{ color: colors.ink, fontWeight: 700 }}>judgement</span>.
        </div>

        {/* Q2b: delayed line — lands ~2.4 s after Q2a */}
        <div
          style={{
            opacity: q2bOp,
            transform: `translateY(${q2bY}px)`,
            fontSize: 28,
            color: colors.ink3,
            maxWidth: 720,
            lineHeight: 1.35,
          }}
        >
          Now try doing it{" "}
          <span style={{ color: colors.accent, fontWeight: 600 }}>
            millions of times
          </span>
          .
        </div>

        {/* Q2c: audience bridge — lands ~2.0 s after Q2b */}
        <div
          style={{
            opacity: q2cOp,
            transform: `translateY(${q2cY}px)`,
            fontSize: 26,
            color: colors.ink3,
            maxWidth: 720,
            lineHeight: 1.35,
          }}
        >
          It's what every robotics team does after every training run.
        </div>
      </div>
    </AbsoluteFill>
  );
};

// Calibration grid: 10×10 mesh + axis labels every 0.1, plus a crosshair at
// (FOOT_X, FOOT_Y). Use this to read off coords in the Studio preview, then
// set FOOT_X / FOOT_Y to the values under the foot you want to highlight.
const CalibrationGrid: React.FC<{ x: number; y: number }> = ({ x, y }) => {
  const ticks = Array.from({ length: 11 }, (_, i) => i / 10);
  return (
    <>
      {ticks.map((t) => (
        <React.Fragment key={`v${t}`}>
          <div
            style={{
              position: "absolute",
              left: `${t * 100}%`,
              top: 0,
              bottom: 0,
              width: 1,
              background: "rgba(255,255,0,0.45)",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: `${t * 100}%`,
              left: 0,
              right: 0,
              height: 1,
              background: "rgba(255,255,0,0.45)",
              pointerEvents: "none",
            }}
          />
        </React.Fragment>
      ))}
      {ticks.map((t) => (
        <div
          key={`xl${t}`}
          style={{
            position: "absolute",
            left: `${t * 100}%`,
            bottom: 4,
            transform: "translateX(-50%)",
            fontFamily: fonts.mono,
            fontSize: 10,
            color: "#ffe900",
            background: "rgba(0,0,0,0.6)",
            padding: "0 3px",
            borderRadius: 2,
            pointerEvents: "none",
          }}
        >
          {t.toFixed(1)}
        </div>
      ))}
      {ticks.map((t) => (
        <div
          key={`yl${t}`}
          style={{
            position: "absolute",
            top: `${t * 100}%`,
            left: 4,
            transform: "translateY(-50%)",
            fontFamily: fonts.mono,
            fontSize: 10,
            color: "#ffe900",
            background: "rgba(0,0,0,0.6)",
            padding: "0 3px",
            borderRadius: 2,
            pointerEvents: "none",
          }}
        >
          {t.toFixed(1)}
        </div>
      ))}
      <div
        style={{
          position: "absolute",
          left: `${x * 100}%`,
          top: 0,
          bottom: 0,
          width: 2,
          background: "#0bff0b",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: `${y * 100}%`,
          left: 0,
          right: 0,
          height: 2,
          background: "#0bff0b",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 8,
          top: 8,
          fontFamily: fonts.mono,
          fontSize: 12,
          color: "#0bff0b",
          background: "rgba(0,0,0,0.7)",
          padding: "4px 8px",
          borderRadius: 4,
          pointerEvents: "none",
        }}
      >
        FOOT_X = {x.toFixed(2)} · FOOT_Y = {y.toFixed(2)}
      </div>
    </>
  );
};

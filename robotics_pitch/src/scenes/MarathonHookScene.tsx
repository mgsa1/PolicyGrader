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

// 0:00–0:18 · Beijing humanoid marathon hook.
//
// The clip plays from 0:02 to 0:04 on the LEFT half of the screen, then
// freezes on the trip frame with a red circle on the robot's left foot.
// Text on the RIGHT phases in over the freeze in two beats:
//   Beat 1 (5–10 s): "What went wrong?" — VO answers orally, hold pause.
//   Beat 2 (10–18 s): "Figuring it fails is easy. Figuring why it fails
//                       requires judgement. Try doing this millions of times."
//
// The clip is 720×768 (vertical-ish). We let it occupy the full left half
// at native aspect, contained inside a 720-wide card.

// ============== TUNE HERE ================================================
// Coordinates of the foot the red dot should highlight, in 0..1 of the clip
// box. Open Remotion Studio, set CALIBRATE = true below, scrub to the freeze
// frame, read off the grid coords under the foot, write them here, set
// CALIBRATE back to false.
const FOOT_X = 0.41;
const FOOT_Y = 0.77;

// Set true to overlay a coordinate grid on the freeze frame for calibration.
// Set back to false before rendering the final video.
const CALIBRATE = false;
// =========================================================================

// Source clip is 30 fps. Play 4.5 s of pre-trip footage from 1.0 s → 5.5 s,
// then freeze on the "just before trip" frame extracted at 5.5 s.
const VIDEO_PLAY_FRAMES = Math.round(4.5 * 30); // 135 frames
const VIDEO_START_FROM = Math.round(1.0 * 30); // start at 1.0 s into source

const Q1_AT = Math.round(7.5 * 30); // "What went wrong?" — 1.5 s after freeze
const Q2_AT = Math.round(12 * 30); // long line — 6.5 s after freeze

export const MarathonHookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Red circle: pulses in at the freeze (scene-frame VIDEO_PLAY_FRAMES).
  const circlePulseScale = interpolate(
    frame,
    [
      VIDEO_PLAY_FRAMES - 6,
      VIDEO_PLAY_FRAMES + 2,
      VIDEO_PLAY_FRAMES + 6,
    ],
    [2.4, 1.0, 1.0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  const circleOp = interpolate(
    frame,
    [VIDEO_PLAY_FRAMES - 6, VIDEO_PLAY_FRAMES + 4],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  // Question 1 — "What went wrong?"
  const q1Op = useFadeIn(frame, Q1_AT, 22);
  const q1Y = interpolate(frame, [Q1_AT, Q1_AT + 28], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  // Q1 dims slightly when Q2 enters — keeps it in view but de-emphasized.
  const q1Fade = interpolate(frame, [Q2_AT - 4, Q2_AT + 18], [1, 0.45], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Question 2 — the long line.
  const q2Op = useFadeIn(frame, Q2_AT, 24);
  const q2Y = interpolate(frame, [Q2_AT, Q2_AT + 30], [24, 0], {
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
          {/* Beat 1: video plays 0:02 → 0:04. */}
          <Sequence from={0} durationInFrames={VIDEO_PLAY_FRAMES}>
            <OffthreadVideo
              src={staticFile("marathon.mp4")}
              startFrom={VIDEO_START_FROM}
              endAt={VIDEO_START_FROM + VIDEO_PLAY_FRAMES}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
              muted
            />
          </Sequence>

          {/* Beat 2: freeze on the trip-frame still for the rest of the scene. */}
          <Sequence from={VIDEO_PLAY_FRAMES}>
            <Img
              src={staticFile("marathon_trip.jpg")}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </Sequence>

          {/* Red circle annotation on the robot's left foot. */}
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

      {/* RIGHT: text overlay (only after the freeze) */}
      <div
        style={{
          flex: 0.95,
          display: "flex",
          flexDirection: "column",
          gap: 32,
          paddingRight: 24,
        }}
      >
        {/* Q1: "What went wrong?" */}
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

        {/* Q2: the long line */}
        <div
          style={{
            opacity: q2Op,
            transform: `translateY(${q2Y}px)`,
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
          <br />
          <br />
          <span style={{ fontSize: 28, color: colors.ink3 }}>
            Now try doing it{" "}
            <span style={{ color: colors.accent, fontWeight: 600 }}>
              millions of times
            </span>
            .
          </span>
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
      {/* Mesh lines */}
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
      {/* X-axis labels along the bottom */}
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
      {/* Y-axis labels along the left */}
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
      {/* Crosshair at current FOOT_X / FOOT_Y */}
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
      {/* Coords readout */}
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

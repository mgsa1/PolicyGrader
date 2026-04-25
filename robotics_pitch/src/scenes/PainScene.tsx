import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  Img,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts, numbers } from "../theme";
import { useFadeIn } from "../components/easing";

// 4–10 s · The pain.
// A wall of 25 robot rollout thumbnails. They get "watched" one by one (gray
// overlay slides in, "$3.75 · 3 min" tag floats up). Counters at top tick to
// the manual-baseline total.
const ALL_FRAMES = [
  ...Array.from({ length: 10 }, (_, i) => `cal_${String(i).padStart(2, "0")}.png`),
  ...Array.from({ length: 15 }, (_, i) => `dep_${String(i).padStart(2, "0")}.png`),
];

const COLS = 5;
const ROWS = 5;
const CELL = 200;
const GAP = 12;

const usd = (n: number) =>
  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

export const PainScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const wallFadeIn = useFadeIn(frame, 4, 18);

  // Each thumbnail "completes" (gray overlay reaches full opacity) over a window.
  // Schedule: stagger across frames 12 .. (durationInFrames - 30).
  const startFrame = 14;
  const endFrame = durationInFrames - 24;
  const totalCells = ALL_FRAMES.length;

  const cellCompleteAt = (i: number) =>
    startFrame + ((endFrame - startFrame) * i) / totalCells;

  // Counter ticks proportional to fraction of cells completed.
  const cellsDone = Math.min(
    totalCells,
    Math.max(
      0,
      Math.floor(
        ((frame - startFrame) / (endFrame - startFrame)) * totalCells,
      ),
    ),
  );
  const dollarsTo =
    (cellsDone / totalCells) * (numbers.manualCostUsd);
  const hoursTo =
    (cellsDone / totalCells) * numbers.manualHours;

  // Final big-number lockup fades in once the last cell darkens.
  const lockupOp = useFadeIn(frame, endFrame - 6, 22);
  const lockupY = interpolate(frame, [endFrame - 6, endFrame + 16], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // Eyebrow + counter
  const counterOp = useFadeIn(frame, 8, 16);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 120,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "row",
        gap: 56,
      }}
    >
      {/* LEFT: counter / explainer */}
      <div
        style={{
          flex: 0.9,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 24,
          opacity: counterOp,
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.6,
            color: colors.ink4,
            textTransform: "uppercase",
          }}
        >
          The pain · pre-deployment sweep
        </div>
        <div
          style={{
            fontSize: 60,
            fontWeight: 600,
            lineHeight: 1.05,
            letterSpacing: -1,
            color: colors.ink,
          }}
        >
          A robotics team
          <br />
          watches{" "}
          <span style={{ color: colors.accent }}>
            {numbers.scenarios.toLocaleString()}
          </span>
          <br />
          rollout videos by hand.
        </div>

        <div
          style={{
            display: "flex",
            gap: 48,
            marginTop: 12,
            fontFamily: fonts.mono,
          }}
        >
          <div>
            <div style={{ fontSize: 11, color: colors.ink4, letterSpacing: 1.4 }}>
              MANUAL COST
            </div>
            <div
              style={{
                fontSize: 56,
                fontWeight: 600,
                color: colors.err,
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1,
                marginTop: 6,
              }}
            >
              {usd(dollarsTo)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: colors.ink4, letterSpacing: 1.4 }}>
              ENGINEER-HOURS
            </div>
            <div
              style={{
                fontSize: 56,
                fontWeight: 600,
                color: colors.err,
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1,
                marginTop: 6,
              }}
            >
              {Math.round(hoursTo)} h
            </div>
          </div>
        </div>

        {/* Final lockup */}
        <div
          style={{
            marginTop: 4,
            opacity: lockupOp,
            transform: `translateY(${lockupY}px)`,
            fontSize: 18,
            color: colors.ink3,
            maxWidth: 460,
            lineHeight: 1.45,
          }}
        >
          Five working weeks. Fifteen thousand dollars. One memo at the end —
          and that&rsquo;s before any policy ships.
        </div>
      </div>

      {/* RIGHT: 5×5 thumbnail wall */}
      <div
        style={{
          flex: 1.1,
          display: "grid",
          gridTemplateColumns: `repeat(${COLS}, ${CELL}px)`,
          gridTemplateRows: `repeat(${ROWS}, ${CELL}px)`,
          gap: GAP,
          alignContent: "center",
          justifyContent: "center",
          opacity: wallFadeIn,
        }}
      >
        {ALL_FRAMES.map((src, i) => {
          const t = cellCompleteAt(i);
          const grayOp = interpolate(frame, [t - 4, t + 6], [0, 0.7], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.22, 1, 0.36, 1),
          });
          const tickOp = interpolate(frame, [t - 2, t + 8], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const ringPulse = interpolate(
            frame,
            [t - 6, t - 2, t + 4],
            [0, 1, 0],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            },
          );

          return (
            <div
              key={src}
              style={{
                position: "relative",
                width: CELL,
                height: CELL,
                borderRadius: 10,
                overflow: "hidden",
                background: colors.surface,
                boxShadow: "0 0 0 1px rgba(31,31,31,0.06)",
              }}
            >
              <Img
                src={staticFile(`keyframes/${src}`)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
              {/* Pulse ring while being "watched" */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  border: `2px solid ${colors.accent}`,
                  borderRadius: 10,
                  opacity: ringPulse,
                  pointerEvents: "none",
                }}
              />
              {/* Gray "watched" overlay */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: "rgba(31,31,31,0.6)",
                  opacity: grayOp,
                  pointerEvents: "none",
                }}
              />
              {/* Tick + price tag */}
              <div
                style={{
                  position: "absolute",
                  bottom: 8,
                  left: 8,
                  right: 8,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  color: "#fff",
                  opacity: tickOp,
                }}
              >
                <span>$3.75</span>
                <span>3 min</span>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

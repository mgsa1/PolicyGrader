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

// 0:18–0:33 · The pain.
//
// Text on the LEFT — "A robotics team watches thousands of rollout videos
// by hand" with a cost counter that ticks up to the manual-baseline total.
// On the RIGHT, a 5×5 wall of rollout thumbnails progressively gets a gray
// "watched" overlay, one cell at a time, until the wall is dimmed.

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

export const PersonalBeatScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const wallFadeIn = useFadeIn(frame, 4, 18);
  const counterOp = useFadeIn(frame, 8, 16);

  // Stagger thumbnails completing across most of the scene's runtime.
  const startFrame = 14;
  const endFrame = durationInFrames - 24;
  const totalCells = ALL_FRAMES.length;

  const cellCompleteAt = (i: number) =>
    startFrame + ((endFrame - startFrame) * i) / totalCells;

  const cellsDone = Math.min(
    totalCells,
    Math.max(
      0,
      Math.floor(((frame - startFrame) / (endFrame - startFrame)) * totalCells),
    ),
  );

  // Counter is qualitative — each cell on the wall represents a *batch* of
  // videos being reviewed, so we ramp into the thousands of dollars and the
  // hundreds of engineer-hours by the end of the scene.
  const PER_CELL_USD = 300;
  const PER_CELL_HOURS = 6;
  const dollarsTo = cellsDone * PER_CELL_USD;
  const hoursTo = cellsDone * PER_CELL_HOURS;

  return (
    <AbsoluteFill
      style={{
        paddingTop: 132,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "row",
        gap: 56,
      }}
    >
      {/* LEFT: copy + cost counter */}
      <div
        style={{
          flex: 0.9,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          gap: 28,
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
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: colors.cal,
              boxShadow: `0 0 12px ${colors.cal}`,
            }}
          />
          The human bottleneck
        </div>

        <div
          style={{
            fontSize: 60,
            fontWeight: 600,
            lineHeight: 1.05,
            letterSpacing: -1.2,
            color: colors.ink,
          }}
        >
          A robotics team watches{" "}
          <span style={{ color: colors.accent }}>thousands</span> of
          <br />
          rollout videos{" "}
          <span style={{ fontStyle: "italic", color: colors.ink2 }}>
            by hand
          </span>
          .
        </div>

        <div
          style={{
            display: "flex",
            gap: 56,
            marginTop: 4,
            fontFamily: fonts.mono,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                color: colors.ink4,
                letterSpacing: 1.6,
                textTransform: "uppercase",
              }}
            >
              Manual cost
            </div>
            <div
              style={{
                fontSize: 64,
                fontWeight: 600,
                color: colors.err,
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1,
                marginTop: 8,
                letterSpacing: -1.4,
              }}
            >
              {usd(dollarsTo)}
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 11,
                color: colors.ink4,
                letterSpacing: 1.6,
                textTransform: "uppercase",
              }}
            >
              Engineer-hours
            </div>
            <div
              style={{
                fontSize: 64,
                fontWeight: 600,
                color: colors.err,
                fontVariantNumeric: "tabular-nums",
                lineHeight: 1,
                marginTop: 8,
                letterSpacing: -1.4,
              }}
            >
              {Math.round(hoursTo)} h
            </div>
          </div>
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
          const ringPulse = interpolate(frame, [t - 6, t - 2, t + 4], [0, 1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

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
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: "rgba(31,31,31,0.6)",
                  opacity: grayOp,
                  pointerEvents: "none",
                }}
              />
              {/* "Watched" check mark — confirms a cell got reviewed without
                  pinning a per-video number that contradicts the headline. */}
              <div
                style={{
                  position: "absolute",
                  bottom: 8,
                  right: 8,
                  width: 22,
                  height: 22,
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.92)",
                  display: "grid",
                  placeItems: "center",
                  fontSize: 12,
                  fontWeight: 700,
                  color: colors.ink,
                  opacity: tickOp,
                }}
              >
                ✓
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

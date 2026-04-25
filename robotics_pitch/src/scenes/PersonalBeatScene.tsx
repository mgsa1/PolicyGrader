import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  OffthreadVideo,
  Loop,
  Sequence,
  staticFile,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 0:18–0:33 · The pain.
//
// LEFT: copy + cost / engineer-hours counter. Both ramp continuously
// LINEARLY against scene frame so they never freeze or cap.
//
// RIGHT: 5-column infinite-feeling list of looping rollout videos.
// The list scrolls upward at a constant rate. Cells flip to grey
// INSTANTLY one-by-one in row-major order (top-left → down). The greying
// rate is synced to scroll so the wave stays near the top of the viewport.
// We define 5 × 20 = 100 logical cells but only render the ~30 currently
// inside the viewport — keeps the simultaneous OffthreadVideo count low.
// At the end of the scene the wall is STILL scrolling and STILL flipping
// — the impression is "this is a tiny window into thousands".

const VIDEO_POOL = [
  "rollouts/cal_01.mp4",
  "rollouts/cal_04.mp4",
  "rollouts/cal_05.mp4",
  "rollouts/cal_08.mp4",
  "rollouts/cal_09.mp4",
  "rollouts/cal_13.mp4",
  "rollouts/cal_17.mp4",
  "rollouts/cal_19.mp4",
  "rollouts/dep_01.mp4",
  "rollouts/dep_03.mp4",
  "rollouts/dep_05.mp4",
  "rollouts/dep_09.mp4",
  "rollouts/dep_13.mp4",
  "rollouts/dep_17.mp4",
  "rollouts/dep_21.mp4",
  "rollouts/dep_29.mp4",
];
const ROLLOUT_LOOP_FRAMES = Math.round(2.7 * 30); // 81

const COLS = 5;
const ROWS = 20; // big enough that scroll never reaches the end inside 15 s
const CELL = 160;
const GAP = 12;
const ROW_PITCH = CELL + GAP; // 172
const VISIBLE_ROWS = 5;
const VIEWPORT_H = VISIBLE_ROWS * CELL + (VISIBLE_ROWS - 1) * GAP; // 848

// Pace: greying advances 1 cell per FRAMES_PER_CELL frames; scroll advances
// in lock-step. With matched rates the grey wave sits at a constant
// viewport-Y = GREY_PRE_ROLL_FRAMES × PX_PER_FRAME — so we give greying a
// head start to push the wave off the top edge (where the vignette would
// hide it) and into the visible middle of the viewport.
const FRAMES_PER_CELL = 6.4;
const PX_PER_FRAME = ROW_PITCH / (FRAMES_PER_CELL * COLS); // ≈ 5.4 px/f
// 75 × 5.375 ≈ 403 px → wave settles at the middle of the 848 px viewport.
// Side effect: at scene start, the first ~2 rows are already grey, which
// reads as "the wave has been running for a while" — appropriate for the beat.
const GREY_PRE_ROLL_FRAMES = 75;

// Counter rates — UNCAPPED. Climb linearly the whole scene.
const USD_PER_FRAME = 22; // ≈ $9 900 over 15 s
const HOURS_PER_FRAME = 0.4; // ≈ 180 h over 15 s

const usd = (n: number) =>
  "$" + Math.round(n).toLocaleString("en-US", { maximumFractionDigits: 0 });

// Deterministic per-cell hash → 0..1.
const cellSeed = (i: number, salt = 0): number => {
  let h = ((i + 1) * 2654435761 + salt * 374761393) >>> 0;
  h = Math.imul(h ^ (h >>> 15), h | 1);
  h ^= h + Math.imul(h ^ (h >>> 7), h | 61);
  return ((h ^ (h >>> 14)) >>> 0) / 4294967296;
};

export const PersonalBeatScene: React.FC = () => {
  const frame = useCurrentFrame();

  const wallFadeIn = useFadeIn(frame, 4, 18);
  const counterOp = useFadeIn(frame, 8, 16);

  const startFrame = 14;
  const elapsedActive = Math.max(0, frame - startFrame);

  // Scroll + grey wave (both linear, both synchronized; grey leads scroll
  // by GREY_PRE_ROLL_FRAMES so the wave sits in the visible middle).
  const scrollY = elapsedActive * PX_PER_FRAME;
  const greyedCells = Math.floor(
    (elapsedActive + GREY_PRE_ROLL_FRAMES) / FRAMES_PER_CELL,
  );

  // UNCAPPED counters.
  const dollarsTo = elapsedActive * USD_PER_FRAME;
  const hoursTo = elapsedActive * HOURS_PER_FRAME;

  // Render only cells whose current viewport-Y is in or near the visible
  // window (one cell of buffer above + below).
  const buffer = ROW_PITCH;
  const visibleCells: { i: number; col: number; viewportY: number; isGrey: boolean }[] =
    [];
  for (let i = 0; i < COLS * ROWS; i++) {
    const row = Math.floor(i / COLS);
    const col = i % COLS;
    const viewportY = row * ROW_PITCH - scrollY;
    if (viewportY > -ROW_PITCH - buffer && viewportY < VIEWPORT_H + buffer) {
      visibleCells.push({ i, col, viewportY, isGrey: i < greyedCells });
    }
  }

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
      {/* LEFT: copy + uncapped cost counter */}
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

      {/* RIGHT: scrolling list (only visible cells rendered) */}
      <div
        style={{
          flex: 1.1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          opacity: wallFadeIn,
        }}
      >
        <div
          style={{
            position: "relative",
            width: COLS * CELL + (COLS - 1) * GAP,
            height: VIEWPORT_H,
            overflow: "hidden",
          }}
        >
          {visibleCells.map(({ i, col, viewportY, isGrey }) => {
            const videoIdx = Math.floor(cellSeed(i, 7) * VIDEO_POOL.length);
            const src = VIDEO_POOL[videoIdx];
            const startOffset = Math.floor(
              cellSeed(i, 13) * ROLLOUT_LOOP_FRAMES,
            );
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: col * (CELL + GAP),
                  top: viewportY,
                  width: CELL,
                  height: CELL,
                  borderRadius: 10,
                  overflow: "hidden",
                  background: colors.surface,
                  boxShadow: "0 0 0 1px rgba(31,31,31,0.06)",
                }}
              >
                <Sequence from={-startOffset}>
                  <Loop durationInFrames={ROLLOUT_LOOP_FRAMES}>
                    <OffthreadVideo
                      src={staticFile(src)}
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                      }}
                      muted
                    />
                  </Loop>
                </Sequence>

                {isGrey ? (
                  <>
                    <div
                      style={{
                        position: "absolute",
                        inset: 0,
                        background: "rgba(31,31,31,0.7)",
                        pointerEvents: "none",
                      }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        bottom: 8,
                        right: 8,
                        width: 20,
                        height: 20,
                        borderRadius: 999,
                        background: "rgba(255,255,255,0.92)",
                        display: "grid",
                        placeItems: "center",
                        fontSize: 11,
                        fontWeight: 700,
                        color: colors.ink,
                      }}
                    >
                      ✓
                    </div>
                  </>
                ) : null}
              </div>
            );
          })}

          {/* Soft top + bottom vignettes so cells fade in/out at the edges
              instead of clipping with hard horizontal lines. */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: 36,
              background:
                "linear-gradient(180deg, rgba(250,250,250,1) 0%, rgba(250,250,250,0) 100%)",
              pointerEvents: "none",
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              height: 36,
              background:
                "linear-gradient(0deg, rgba(250,250,250,1) 0%, rgba(250,250,250,0) 100%)",
              pointerEvents: "none",
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  Img,
  OffthreadVideo,
  Loop,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 1:40–1:53 · Two challenges with the judge — and the prompt engineering
// that fixed them.
//
// Scene length: 16 s (480 frames @ 30 fps). Four stages told in sequence,
// all on a single keyframe canvas so the eye stays put while the chips and
// the right-side card carry the meaning. Stage durations are scaled
// uniformly from the original 13 s pacing (×16/13):
//   1. setup       (0-74,    2.5 s) — pointing puts the failure on the pixel.
//   2. problem     (74-197,  4.1 s) — forced to point with no contact, the
//                                     dot landed at random — on every
//                                     missed_approach we ran.
//   3. abstention  (197-320, 4.1 s) — `point = null` is a first-class output;
//                                     the keyframe stays honest.
//   4. telemetry   (320-480, 5.3 s) — where vision was still ambiguous, the
//                                     user message includes per-step
//                                     simulator telemetry; the judge reasons
//                                     over pixels and physics together.
//
// All keyframes / video / telemetry rows are real outputs from
// artifacts/runs/eval_d5a040 — the bug was real, the fixes are real. See
// `_render_telemetry_block` in src/vision/judge.py and CLAUDE.md §16.
//
// Face PiP corner: this scene runs without a face overlay (see Hero.tsx
// SCENE_PLAN entry); the right side carries the telemetry table without a
// face-cam zone to clear.

const STAGES = {
  setup: { from: 0, to: 74 },
  problem: { from: 74, to: 197 },
  resolution: { from: 197, to: 320 },
  telemetry: { from: 320, to: 480 },
} as const;

// Real findings.jsonl entries (eval_d5a040). The PROBLEM_FRAME's baked-in
// red dot is the model's actual pre-fix output — it was forced to point
// even though there was no contact, so the coordinate is arbitrary.
const SETUP_FRAME = {
  src: "keyframes/cal_04.png",
  point: [957, 1101] as const,
  taxonomy: "failed_grip",
};
const PROBLEM_FRAME = {
  src: "keyframes/cal_06.png",
  point: [1003, 1108] as const,
};

// cal_09 is a real missed_approach. We play the underlying mp4 (no overlay)
// to show what the keyframe renders when the judge abstains.
const RESOLUTION_VIDEO_SRC = "rollouts/cal_09.mp4";
const RESOLUTION_VIDEO_LOOP_FRAMES = 100;

// Real cal_04 telemetry rows (sampled from cal_04.telemetry.json). The
// contact column flipping ✓ → - between rows 4 and 5 is the slip moment —
// the kind of sub-second event a vision-only pass can lose between sampled
// frames, but telemetry catches.
const TELEMETRY_ROWS = [
  { f: 0, grip: "0.00", ee: "0.213", cz: "-0.012", cxy: "0.000", contact: "-" },
  { f: 10, grip: "0.00", ee: "0.099", cz: "-0.010", cxy: "0.000", contact: "-" },
  { f: 20, grip: "0.00", ee: "0.020", cz: "-0.010", cxy: "0.000", contact: "-" },
  { f: 31, grip: "0.00", ee: "0.005", cz: "+0.004", cxy: "0.001", contact: "✓" },
  { f: 41, grip: "0.00", ee: "0.005", cz: "+0.129", cxy: "0.001", contact: "✓" },
  { f: 52, grip: "0.00", ee: "0.183", cz: "+0.018", cxy: "0.005", contact: "-" },
] as const;

export const JudgeChallengesScene: React.FC = () => {
  const frame = useCurrentFrame();

  const inSetup = frame >= STAGES.setup.from && frame < STAGES.setup.to;
  const inProblem = frame >= STAGES.problem.from && frame < STAGES.problem.to;
  const inResolution =
    frame >= STAGES.resolution.from && frame < STAGES.resolution.to;
  const inTelemetry = frame >= STAGES.telemetry.from;

  const headerOp = useFadeIn(frame, 0, 20);

  const setupOp = interpolate(
    frame,
    [STAGES.setup.from, STAGES.setup.from + 12, STAGES.setup.to - 10, STAGES.setup.to],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const problemOp = interpolate(
    frame,
    [
      STAGES.problem.from,
      STAGES.problem.from + 12,
      STAGES.problem.to - 10,
      STAGES.problem.to,
    ],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const resolutionOp = interpolate(
    frame,
    [
      STAGES.resolution.from,
      STAGES.resolution.from + 17,
      STAGES.resolution.to - 10,
      STAGES.resolution.to,
    ],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const telemetryOp = interpolate(
    frame,
    [STAGES.telemetry.from, STAGES.telemetry.from + 17],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const nullChipScale = interpolate(
    frame,
    [STAGES.resolution.from + 17, STAGES.resolution.from + 37],
    [0.85, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  const stageLabel = inSetup
    ? "01 · contact"
    : inProblem
      ? "02 · the bug"
      : inResolution
        ? "03 · abstention"
        : "04 · telemetry context";

  return (
    <AbsoluteFill
      style={{
        paddingTop: 124,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "column",
        gap: 22,
      }}
    >
      {/* Header */}
      <div style={{ opacity: headerOp }}>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.6,
            color: colors.ink4,
            textTransform: "uppercase",
          }}
        >
          Two challenges · prompt engineering
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 48,
            fontWeight: 600,
            letterSpacing: -0.8,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          Vision wasn&rsquo;t enough.{" "}
          <span style={{ color: colors.accent }}>
            We taught the judge when not to point —
          </span>{" "}
          <span style={{ color: colors.phaseJudge }}>
            and gave it physics to read.
          </span>
        </div>
      </div>

      {/* Stage strip + body */}
      <div
        style={{
          flex: 1,
          position: "relative",
          background: colors.surface,
          border: `1px solid ${colors.line}`,
          borderRadius: 16,
          padding: 26,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {/* Stage chip */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 1.6,
            color: colors.ink4,
            textTransform: "uppercase",
          }}
        >
          <span style={{ color: colors.phaseJudge, fontWeight: 600 }}>
            ● {stageLabel}
          </span>
          <span>findings.jsonl · live</span>
        </div>

        {/* Stages 1-3: 1:1 keyframe stack with overlay chips. Hidden during
            stage 4. */}
        <div
          style={{
            alignSelf: "center",
            width: 560,
            height: 560,
            borderRadius: 14,
            overflow: "hidden",
            background: "#000",
            position: "relative",
            boxShadow: "0 18px 40px rgba(31,31,31,0.10)",
            opacity: inTelemetry ? 0 : 1,
          }}
        >
          {/* Stage 1: failed_grip with real baked-in red dot */}
          <div style={{ position: "absolute", inset: 0, opacity: setupOp }}>
            <Img
              src={staticFile(SETUP_FRAME.src)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </div>

          {/* Stage 2: a real missed_approach keyframe whose baked-in dot was
              drawn at an arbitrary pixel because the model was forced to point. */}
          <div style={{ position: "absolute", inset: 0, opacity: problemOp }}>
            <Img
              src={staticFile(PROBLEM_FRAME.src)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </div>

          {/* Stage 3: real missed_approach video, no overlay — the
              abstention render. */}
          <div style={{ position: "absolute", inset: 0, opacity: resolutionOp }}>
            <Loop durationInFrames={RESOLUTION_VIDEO_LOOP_FRAMES}>
              <OffthreadVideo
                src={staticFile(RESOLUTION_VIDEO_SRC)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                muted
              />
            </Loop>
          </div>

          {/* Stage 1 chip */}
          <div
            style={{
              opacity: setupOp,
              position: "absolute",
              left: 14,
              bottom: 14,
            }}
          >
            <span
              style={{
                fontFamily: fonts.mono,
                fontSize: 14,
                padding: "7px 14px",
                borderRadius: 6,
                background: "rgba(0,0,0,0.55)",
                color: "#fff",
                fontWeight: 600,
                letterSpacing: 0.4,
              }}
            >
              point = ({SETUP_FRAME.point[0]}, {SETUP_FRAME.point[1]})
            </span>
          </div>

          {/* Stage 2 chip — emphasises that the coordinate is meaningless. */}
          <div
            style={{
              opacity: problemOp,
              position: "absolute",
              left: 14,
              bottom: 14,
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontFamily: fonts.mono,
                fontSize: 14,
                padding: "7px 14px",
                borderRadius: 6,
                background: "rgba(179, 38, 30, 0.85)",
                color: "#fff",
                fontWeight: 600,
                letterSpacing: 0.4,
              }}
            >
              point = ({PROBLEM_FRAME.point[0]}, {PROBLEM_FRAME.point[1]}) ·{" "}
              <span style={{ opacity: 0.85 }}>random</span>
            </span>
          </div>

          {/* Stage 3 chip */}
          <div
            style={{
              opacity: resolutionOp,
              transform: `scale(${nullChipScale})`,
              transformOrigin: "left bottom",
              position: "absolute",
              left: 14,
              bottom: 14,
              display: "flex",
              gap: 8,
            }}
          >
            <span
              style={{
                fontFamily: fonts.mono,
                fontSize: 16,
                padding: "9px 16px",
                borderRadius: 6,
                background: colors.ok,
                color: "#fff",
                fontWeight: 700,
                letterSpacing: 0.4,
                boxShadow: `0 0 0 3px ${colors.okSoft}`,
              }}
            >
              point = null
            </span>
            <span
              style={{
                fontFamily: fonts.mono,
                fontSize: 13,
                padding: "9px 14px",
                borderRadius: 6,
                background: "rgba(0,0,0,0.55)",
                color: "#fff",
              }}
            >
              judge abstains
            </span>
          </div>
        </div>

        {/* Stage 4: side-by-side keyframe + ASCII telemetry table. */}
        <div
          style={{
            opacity: telemetryOp,
            position: "absolute",
            top: 80,
            left: 26,
            right: 26,
            bottom: 130,
            display: "flex",
            gap: 24,
            alignItems: "stretch",
          }}
        >
          {/* Left: cal_04 keyframe (with the real baked-in dot — contact
              existed for this rollout). */}
          <div
            style={{
              width: 460,
              borderRadius: 14,
              overflow: "hidden",
              background: "#000",
              position: "relative",
              boxShadow: "0 14px 30px rgba(31,31,31,0.10)",
              flexShrink: 0,
            }}
          >
            <Img
              src={staticFile(SETUP_FRAME.src)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
            <div
              style={{
                position: "absolute",
                left: 12,
                bottom: 12,
                fontFamily: fonts.mono,
                fontSize: 13,
                padding: "6px 12px",
                borderRadius: 6,
                background: "rgba(0,0,0,0.55)",
                color: "#fff",
              }}
            >
              cal_04 · failed_grip
            </div>
          </div>

          {/* Right: ASCII telemetry table card — the user message the judge
              actually receives. */}
          <div
            style={{
              flex: 1,
              background: "#0e1116",
              border: `1px solid ${colors.line}`,
              borderRadius: 14,
              padding: 22,
              fontFamily: fonts.mono,
              fontSize: 16,
              color: "#a8c7fa",
              display: "flex",
              flexDirection: "column",
              gap: 8,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                fontSize: 11,
                letterSpacing: 1.6,
                color: "#6f7681",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              ● user message · sim telemetry block
            </div>
            <div style={{ color: "#9aa0a6", lineHeight: 1.4, fontSize: 14 }}>
              Sim telemetry (one row per shown frame — exact, from simulator):
            </div>
            <div style={{ color: "#6f7681", lineHeight: 1.6 }}>
              Frame  gripper  ee→cube  cube_z   cube_xy   contact
            </div>
            {TELEMETRY_ROWS.map((r, i) => {
              const rowStart = STAGES.telemetry.from + 22 + i * 11;
              const rowOp = interpolate(
                frame,
                [rowStart, rowStart + 12],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
              );
              const isSlipRow = i === 4 || i === 5;
              return (
                <div
                  key={r.f}
                  style={{
                    opacity: rowOp,
                    color: isSlipRow ? "#ffd166" : "#e8eaed",
                    lineHeight: 1.6,
                    letterSpacing: 0.3,
                  }}
                >
                  {String(r.f).padStart(5, " ")}  {r.grip}    {r.ee}m   {r.cz}m   {r.cxy}m   {r.contact}
                </div>
              );
            })}
            <div
              style={{
                opacity: interpolate(
                  frame,
                  [STAGES.telemetry.from + 98, STAGES.telemetry.from + 123],
                  [0, 1],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                ),
                marginTop: "auto",
                fontSize: 14,
                color: "#ffd166",
                lineHeight: 1.5,
              }}
            >
              ↳ contact ✓ → − between f41 and f52 = slip. The judge reads the
              same physics the simulator did.
            </div>
          </div>
        </div>

        {/* Bottom caption — fades through stages. Positioned above the face
            PiP zone (this scene has no face cam, so no clearance issue). */}
        <div
          style={{
            position: "relative",
            marginTop: "auto",
            fontFamily: fonts.sans,
            fontSize: 18,
            color: colors.ink2,
            lineHeight: 1.4,
            minHeight: 56,
          }}
        >
          <span style={{ opacity: setupOp, position: "absolute", left: 0, top: 0 }}>
            The judge points at the failure. Real coordinate, real pixel.
          </span>
          <span style={{ opacity: problemOp, position: "absolute", left: 0, top: 0 }}>
            Forced to point with no contact, the dot landed at random —{" "}
            <strong style={{ color: colors.err }}>on every</strong>{" "}
            missed_approach.
          </span>
          <span
            style={{ opacity: resolutionOp, position: "absolute", left: 0, top: 0 }}
          >
            <strong style={{ color: colors.ok }}>Abstention</strong> — first-class
            output. The keyframe stays honest.
          </span>
          <span
            style={{ opacity: telemetryOp, position: "absolute", left: 0, top: 0 }}
          >
            <strong style={{ color: colors.accent }}>
              Telemetry pasted as context
            </strong>{" "}
            — pixels grounded by physics. Prompt-engineered, on disk.
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

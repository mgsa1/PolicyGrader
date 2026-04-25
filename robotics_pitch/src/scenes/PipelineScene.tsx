import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  OffthreadVideo,
  Loop,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";
import { PhaseCard } from "../components/PhaseCard";

// 0:48–1:10 · The pipeline.
//
// Five phase cards anchor the architecture (planner / rollout / labeling /
// judge / reporter). Below them, an animated flow shows what actually
// travels along the pipe:
//
//   prompt  →  rollout videos  →  K judge sessions  →  report.md
//
// Each beat of the flow lights up one of the phase cards above, so the
// viewer maps the abstraction (cards) to the concrete data (boxes below).
// No "submit_*" prose — the picture carries the message.

const PHASES = [
  {
    number: "01",
    name: "Planner",
    artifact: "plan.md · test_matrix.csv",
    detail: "Designs the test suite from a one-line English goal.",
    color: colors.phasePlanner,
  },
  {
    number: "02",
    name: "Rollout",
    artifact: "rollouts/*.mp4",
    detail: "Runs the policy in robosuite + MuJoCo. Records video & telemetry.",
    color: colors.phaseRollout,
  },
  {
    number: "03",
    name: "Labeling",
    artifact: "human_labels.jsonl",
    detail: "Human labels a sampled subset — calibration ground truth.",
    color: colors.phaseLabeling,
    badge: "human · gradio",
  },
  {
    number: "04",
    name: "Judge",
    artifact: "findings.jsonl",
    detail: "Vision judge: 2576-px frames, names failure, points or abstains.",
    color: colors.phaseJudge,
    badge: "×K parallel",
  },
  {
    number: "05",
    name: "Reporter",
    artifact: "report.md",
    detail: "Clusters every failure across the run inside a 1 M context.",
    color: colors.phaseReport,
  },
];

const STAGGER = 14;

// Real rollout videos from the last eval run — mix of successful (cal_01,
// cal_05, dep_05, dep_13) and failed (cal_09, cal_13, dep_29, cal_04). Each
// clip is 2.7 s @ 30 fps; we Loop them so they always look like a live run.
export const ROLLOUT_VIDEOS: { src: string; outcome: "pass" | "fail" }[] = [
  { src: "rollouts/cal_01.mp4", outcome: "pass" },
  { src: "rollouts/cal_09.mp4", outcome: "fail" },
  { src: "rollouts/dep_05.mp4", outcome: "pass" },
  { src: "rollouts/cal_13.mp4", outcome: "fail" },
  { src: "rollouts/cal_05.mp4", outcome: "pass" },
  { src: "rollouts/dep_29.mp4", outcome: "fail" },
  { src: "rollouts/dep_13.mp4", outcome: "pass" },
  { src: "rollouts/cal_04.mp4", outcome: "fail" },
];
export const ROLLOUT_LOOP_FRAMES = Math.round(2.7 * 30); // 81 frames per video

export const PROMPT_TEXT = "Evaluate Lift policy under cube_xy_jitter_m=0.15";

export const PipelineScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOp = useFadeIn(frame, 0, 18);

  // All cards have landed by this frame.
  const cardsLandedAt = 20 + (PHASES.length - 1) * STAGGER + 22;

  // Flow animation timeline (after cards land).
  const T_PROMPT_TYPED = cardsLandedAt + 8; // prompt finishes typing
  const T_ROLLOUTS_OUT = T_PROMPT_TYPED + 18; // first thumb appears
  const T_JUDGES_OUT = T_ROLLOUTS_OUT + 30; // judges start receiving
  const T_REPORT_OUT = T_JUDGES_OUT + 28; // reporter consolidates

  return (
    <AbsoluteFill
      style={{
        paddingTop: 132,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "column",
      }}
    >
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
          Automated embodied AI evaluation orchestrator · k-managed agents
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 50,
            fontWeight: 600,
            letterSpacing: -1,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          <span style={{ color: colors.accent }}>K</span>-managed Opus 4.7 agents.{" "}
          <span style={{ color: colors.accent }}>One pipeline.</span>
        </div>
      </div>

      {/* Phase cards row */}
      <div
        style={{
          marginTop: 38,
          display: "flex",
          alignItems: "stretch",
          gap: 14,
        }}
      >
        {PHASES.map((p, i) => (
          <PhaseCard
            key={p.number}
            index={i}
            total={PHASES.length}
            number={p.number}
            name={p.name.toUpperCase()}
            artifact={p.artifact}
            detail={p.detail}
            color={p.color}
            delayFrames={20 + i * STAGGER}
            badge={p.badge}
          />
        ))}
      </div>

      {/* Animated flow underneath: prompt → rollouts → K judges → report */}
      <div
        style={{
          marginTop: 36,
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1.1fr 28px 1.4fr 28px 1.1fr 28px 0.9fr",
          alignItems: "center",
          gap: 0,
        }}
      >
        {/* 1. Prompt */}
        <PromptBox
          text={PROMPT_TEXT}
          enterAt={cardsLandedAt}
          finishAt={T_PROMPT_TYPED}
          frame={frame}
        />

        <Arrow color={colors.phasePlanner} activeAt={T_PROMPT_TYPED} frame={frame} />

        {/* 2. Rollout videos */}
        <RolloutsBox enterAt={T_ROLLOUTS_OUT} frame={frame} />

        <Arrow color={colors.phaseJudge} activeAt={T_JUDGES_OUT} frame={frame} />

        {/* 3. K judge sessions */}
        <JudgesBox enterAt={T_JUDGES_OUT} frame={frame} />

        <Arrow color={colors.phaseReport} activeAt={T_REPORT_OUT} frame={frame} />

        {/* 4. report.md */}
        <ReportBox enterAt={T_REPORT_OUT} frame={frame} />
      </div>
    </AbsoluteFill>
  );
};

// ---------------- Flow boxes ---------------------------------------------

export const PromptBox: React.FC<{
  text: string;
  enterAt: number;
  finishAt: number;
  frame: number;
}> = ({ text, enterAt, finishAt, frame }) => {
  const op = useFadeIn(frame, enterAt, 14);
  const charsVisible = Math.max(
    0,
    Math.min(
      text.length,
      Math.floor(((frame - enterAt) / (finishAt - enterAt)) * text.length),
    ),
  );
  // Cursor blinks while typing.
  const showCursor = frame >= enterAt && frame < finishAt + 30 && (frame % 30 < 18);
  return (
    <div
      style={{
        opacity: op,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 12,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        boxShadow: "0 4px 14px rgba(31,31,31,0.04)",
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 10,
          letterSpacing: 1.8,
          color: colors.phasePlanner,
          textTransform: "uppercase",
          fontWeight: 600,
        }}
      >
        ● prompt
      </div>
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 14,
          color: colors.ink,
          lineHeight: 1.45,
          minHeight: 60,
        }}
      >
        {text.slice(0, charsVisible)}
        {showCursor ? (
          <span style={{ color: colors.accent }}>▍</span>
        ) : null}
      </div>
    </div>
  );
};

export const RolloutsBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => {
  return (
    <div
      style={{
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 12,
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          opacity: useFadeIn(frame, enterAt - 4, 14),
          fontFamily: fonts.mono,
          fontSize: 10,
          letterSpacing: 1.8,
          color: colors.phaseRollout,
          textTransform: "uppercase",
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>● rollouts</span>
        <span style={{ color: colors.ink4 }}>video × N</span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 6,
        }}
      >
        {ROLLOUT_VIDEOS.map((v, i) => {
          const delay = enterAt + i * 4;
          const op = interpolate(frame, [delay, delay + 12], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.22, 1, 0.36, 1),
          });
          const scale = interpolate(frame, [delay, delay + 16], [0.9, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.22, 1, 0.36, 1),
          });
          const ringColor = v.outcome === "pass" ? colors.ok : colors.err;
          return (
            <div
              key={v.src}
              style={{
                position: "relative",
                opacity: op,
                transform: `scale(${scale})`,
                aspectRatio: "1 / 1",
                borderRadius: 6,
                overflow: "hidden",
                background: colors.surface2,
                boxShadow: `0 0 0 1.5px ${ringColor}aa`,
              }}
            >
              <Loop durationInFrames={ROLLOUT_LOOP_FRAMES}>
                <OffthreadVideo
                  src={staticFile(v.src)}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  muted
                />
              </Loop>
              <div
                style={{
                  position: "absolute",
                  bottom: 4,
                  right: 4,
                  fontFamily: fonts.mono,
                  fontSize: 8,
                  letterSpacing: 1.0,
                  padding: "1px 5px",
                  borderRadius: 3,
                  background: ringColor,
                  color: "#fff",
                  textTransform: "uppercase",
                  fontWeight: 700,
                }}
              >
                {v.outcome}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const JudgesBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => {
  // Four "judge worker" mini-terminals stacked vertically.
  const workers = [
    { id: "judge-1", lines: ["→ rollout=cal_07", "← failed_grip", "  point=(403,312)"] },
    { id: "judge-2", lines: ["→ rollout=dep_14", "← missed_approach", "  point=null"] },
    { id: "judge-3", lines: ["→ rollout=dep_02", "← failed_grip", "  point=(388,294)"] },
    { id: "judge-4", lines: ["→ rollout=dep_11", "← missed_approach", "  point=null"] },
  ];
  return (
    <div
      style={{
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 12,
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div
        style={{
          opacity: useFadeIn(frame, enterAt - 4, 14),
          fontFamily: fonts.mono,
          fontSize: 10,
          letterSpacing: 1.8,
          color: colors.phaseJudge,
          textTransform: "uppercase",
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>● judges</span>
        <span style={{ color: colors.ink4 }}>K parallel · 4 of K shown</span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 6,
        }}
      >
        {workers.map((w, i) => {
          const delay = enterAt + i * 6;
          const op = useFadeIn(frame, delay, 14);
          const visibleLines = Math.max(
            0,
            Math.min(w.lines.length, Math.floor((frame - delay) / 10)),
          );
          return (
            <div
              key={w.id}
              style={{
                opacity: op,
                background: "#0e1116",
                borderRadius: 6,
                padding: "8px 10px",
                fontFamily: fonts.mono,
                fontSize: 9,
                color: "#a8c7fa",
                lineHeight: 1.45,
              }}
            >
              <div
                style={{
                  fontSize: 8,
                  color: "#6f7681",
                  letterSpacing: 1.2,
                  textTransform: "uppercase",
                  marginBottom: 4,
                }}
              >
                ● {w.id}
              </div>
              {w.lines.slice(0, visibleLines).map((l, li) => (
                <div
                  key={li}
                  style={{
                    color: l.startsWith("←")
                      ? "#137333"
                      : l.startsWith("→")
                        ? "#a8c7fa"
                        : "#9aa0a6",
                  }}
                >
                  {l}
                </div>
              ))}
            </div>
          );
        })}
      </div>
      {/* +k hint — there are as many judges as the user asked for. */}
      <div
        style={{
          opacity: useFadeIn(frame, enterAt + workers.length * 6 + 8, 16),
          marginTop: 4,
          padding: "6px 8px",
          border: `1px dashed ${colors.phaseJudge}80`,
          borderRadius: 6,
          background: `${colors.phaseJudge}0d`,
          fontFamily: fonts.mono,
          fontSize: 9,
          color: colors.phaseJudge,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          textAlign: "center",
          fontWeight: 600,
        }}
      >
        + K − 4 more sessions ⋯
      </div>
    </div>
  );
};

export const ReportBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => {
  const op = useFadeIn(frame, enterAt, 16);
  const lines = [
    { at: 0, text: "# Eval Report", weight: 700 },
    { at: 6, text: "## Findings", weight: 600 },
    { at: 12, text: "Cluster 1: missed_approach (612)" },
    { at: 18, text: "Cluster 2: failed_grip (388)" },
    { at: 24, text: "Cluster 3: lateral overshoot (142)" },
    { at: 30, text: "## Judge Trust" },
    { at: 36, text: "P = 91% · R = 87%" },
  ];
  return (
    <div
      style={{
        opacity: op,
        background: colors.surface,
        border: `1px solid ${colors.phaseReport}`,
        borderRadius: 12,
        padding: 14,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        boxShadow: `0 0 0 4px ${colors.phaseReport}14`,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 10,
          letterSpacing: 1.8,
          color: colors.phaseReport,
          textTransform: "uppercase",
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span>● report.md</span>
        <span style={{ color: colors.ink4 }}>1 M ctx</span>
      </div>
      {lines.map((l, i) => {
        const lineOp = useFadeIn(frame, enterAt + l.at, 10);
        return (
          <div
            key={i}
            style={{
              opacity: lineOp,
              fontFamily: fonts.mono,
              fontSize: l.weight ? 11 : 10,
              fontWeight: l.weight ?? 400,
              color: l.weight ? colors.ink : colors.ink3,
              lineHeight: 1.4,
            }}
          >
            {l.text}
          </div>
        );
      })}
    </div>
  );
};

export const Arrow: React.FC<{ color: string; activeAt: number; frame: number }> = ({
  color,
  activeAt,
  frame,
}) => {
  const op = useFadeIn(frame, activeAt - 6, 14);
  // Token slides along the arrow once.
  const tokenT = interpolate(
    frame,
    [activeAt - 4, activeAt + 14],
    [-0.2, 1.2],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  return (
    <div style={{ position: "relative", height: 24, opacity: op }}>
      <div
        style={{
          position: "absolute",
          top: 11,
          left: 0,
          right: 0,
          height: 2,
          background: color,
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 4,
          right: -2,
          width: 0,
          height: 0,
          borderLeft: `8px solid ${color}`,
          borderTop: "8px solid transparent",
          borderBottom: "8px solid transparent",
        }}
      />
      {tokenT >= 0 && tokenT <= 1 ? (
        <div
          style={{
            position: "absolute",
            top: 6,
            left: `${tokenT * 100}%`,
            width: 12,
            height: 12,
            marginLeft: -6,
            borderRadius: 999,
            background: "#fff",
            boxShadow: `0 0 0 2px ${color}, 0 0 12px ${color}`,
          }}
        />
      ) : null}
    </div>
  );
};

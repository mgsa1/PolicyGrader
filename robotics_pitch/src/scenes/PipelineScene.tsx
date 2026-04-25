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
// Five phase cards anchor the architecture; below them an animated flow
// shows the data moving:
//   prompt → rollout videos → K judge sessions → report.md
//
// Per-rollout failure-analysis lives in its OWN downstream scene (Sequence 5,
// JudgeAnalysisScene), so this scene stays focused on the pipeline picture.

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

// Two stacks: SIMULATION (Planner + Rollout) and AI ANALYSIS (Labeling + Judge
// + Reporter). The reveal is paced for voice-over — each card lands with room
// to introduce, and the two groups are separated by a deliberate beat so the
// stack handoff reads on screen.
const STAGGER = 36; // 1.2 s between cards within a group
const GROUP_GAP = 60; // extra 2 s pause between sim and ai groups
const CARD_LAND_AFTER = 28; // PhaseCard slide + artifact reveal duration

const CARD_DELAYS = [
  20, // 01 Planner    (sim)
  20 + STAGGER, // 02 Rollout    (sim)
  20 + 2 * STAGGER + GROUP_GAP, // 03 Labeling   (ai)
  20 + 3 * STAGGER + GROUP_GAP, // 04 Judge      (ai)
  20 + 4 * STAGGER + GROUP_GAP, // 05 Reporter   (ai)
];
const SIM_BRACKET_AT = 12;
const AI_BRACKET_AT = CARD_DELAYS[2] - 10;

// Anthropic coral — used for the Claude sparkle mark and the AI-stack wash.
const ANTHROPIC_CORAL = "#cc785c";

export const ROLLOUT_VIDEOS: { src: string; outcome: "pass" | "fail" }[] = [
  { src: "rollouts/cal_05.mp4", outcome: "pass" },
  { src: "rollouts/dep_29.mp4", outcome: "fail" },
  { src: "rollouts/dep_13.mp4", outcome: "pass" },
  { src: "rollouts/cal_09.mp4", outcome: "fail" },
  { src: "rollouts/cal_13.mp4", outcome: "fail" },
  { src: "rollouts/cal_01.mp4", outcome: "pass" },
  { src: "rollouts/cal_04.mp4", outcome: "fail" },
  { src: "rollouts/dep_05.mp4", outcome: "pass" },
];
export const ROLLOUT_LOOP_FRAMES = Math.round(2.7 * 30);

export const PROMPT_TEXT = "Evaluate Lift policy under cube_xy_jitter_m=0.15";

export const PipelineScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOp = useFadeIn(frame, 0, 18);

  // After the last AI card lands, hold so the audience absorbs the full stack
  // before the data flow kicks off.
  const cardsLandedAt = CARD_DELAYS[CARD_DELAYS.length - 1] + CARD_LAND_AFTER;
  const HOLD_AFTER_CARDS = 60;
  const T_PROMPT_ENTER = cardsLandedAt + HOLD_AFTER_CARDS;
  const T_PROMPT_TYPED = T_PROMPT_ENTER + 20;
  const T_ROLLOUTS_OUT = T_PROMPT_TYPED + 30;
  const T_JUDGES_OUT = T_ROLLOUTS_OUT + 50;
  const T_REPORT_OUT = T_JUDGES_OUT + 45;

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

      <div style={{ marginTop: 38 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(5, 1fr)",
            gap: 14,
            marginBottom: 18,
          }}
        >
          <StackBracket
            label="Simulation Stack"
            enterAt={SIM_BRACKET_AT}
            frame={frame}
            style={{ gridColumn: "1 / span 2" }}
          />
          <StackBracket
            label="AI Analysis Stack"
            enterAt={AI_BRACKET_AT}
            frame={frame}
            style={{ gridColumn: "3 / span 3" }}
            icon={<ClaudeMark size={13} color={ANTHROPIC_CORAL} />}
          />
        </div>
        <div style={{ position: "relative" }}>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              gridTemplateColumns: "repeat(5, 1fr)",
              gap: 14,
              pointerEvents: "none",
              zIndex: 0,
            }}
          >
            <AnthropicWash enterAt={AI_BRACKET_AT} frame={frame} />
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(5, 1fr)",
              gap: 14,
              alignItems: "stretch",
              position: "relative",
              zIndex: 1,
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
                delayFrames={CARD_DELAYS[i]}
                badge={p.badge}
              />
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 42,
          height: 340,
          display: "grid",
          gridTemplateColumns: "1.1fr 28px 1.4fr 28px 1.1fr 28px 0.9fr",
          alignItems: "stretch",
          gap: 0,
        }}
      >
        <PromptBox
          text={PROMPT_TEXT}
          enterAt={T_PROMPT_ENTER}
          finishAt={T_PROMPT_TYPED}
          frame={frame}
        />
        <Arrow color={colors.phasePlanner} activeAt={T_PROMPT_TYPED} frame={frame} />
        <RolloutsBox enterAt={T_ROLLOUTS_OUT} frame={frame} />
        <Arrow color={colors.phaseJudge} activeAt={T_JUDGES_OUT} frame={frame} />
        <JudgesBox enterAt={T_JUDGES_OUT} frame={frame} />
        <Arrow color={colors.phaseReport} activeAt={T_REPORT_OUT} frame={frame} />
        <ReportBox enterAt={T_REPORT_OUT} frame={frame} />
      </div>
    </AbsoluteFill>
  );
};

// ---- Anthropic-flavoured AI Analysis underlay ---------------------------

const ClaudeMark: React.FC<{ size: number; color: string }> = ({
  size,
  color,
}) => (
  <svg
    viewBox="0 0 24 24"
    width={size}
    height={size}
    style={{ display: "block" }}
    aria-hidden
  >
    <path
      d="M12 0 L13.2 8.5 L19.8 4.2 L15.5 10.8 L24 12 L15.5 13.2 L19.8 19.8 L13.2 15.5 L12 24 L10.8 15.5 L4.2 19.8 L8.5 13.2 L0 12 L8.5 10.8 L4.2 4.2 L10.8 8.5 Z"
      fill={color}
    />
  </svg>
);

const AnthropicWash: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => {
  const op = useFadeIn(frame, enterAt, 22);
  return (
    <div
      style={{
        gridColumn: "3 / span 3",
        gridRow: 1,
        background:
          "linear-gradient(180deg, rgba(204,120,92,0.09) 0%, rgba(204,120,92,0.04) 100%)",
        borderRadius: 18,
        margin: "-14px -8px",
        opacity: op,
        pointerEvents: "none",
      }}
    />
  );
};

// ---- Stack bracket (groups phase cards into Simulation / AI Analysis) ---

const StackBracket: React.FC<{
  label: string;
  enterAt: number;
  frame: number;
  style?: React.CSSProperties;
  icon?: React.ReactNode;
}> = ({ label, enterAt, frame, style, icon }) => {
  const op = useFadeIn(frame, enterAt, 18);
  const dropY = interpolate(frame, [enterAt, enterAt + 22], [-6, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  return (
    <div
      style={{
        ...style,
        opacity: op,
        transform: `translateY(${dropY}px)`,
        position: "relative",
        height: 30,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 15,
          left: 0,
          right: 0,
          height: 1,
          background: colors.line2,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 15,
          left: 0,
          width: 1,
          height: 15,
          background: colors.line2,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 15,
          right: 0,
          width: 1,
          height: 15,
          background: colors.line2,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 0,
          left: "50%",
          transform: "translateX(-50%)",
          background: colors.bg,
          padding: "0 16px",
          fontFamily: fonts.mono,
          fontSize: 12,
          letterSpacing: 2.4,
          color: colors.ink4,
          textTransform: "uppercase",
          fontWeight: 600,
          whiteSpace: "nowrap",
          lineHeight: "30px",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        {icon}
        {label}
      </div>
    </div>
  );
};

// ---- Flow boxes ---------------------------------------------------------

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
  const showCursor =
    frame >= enterAt && frame < finishAt + 30 && frame % 30 < 18;
  return (
    <div
      style={{
        opacity: op,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 10,
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: 1.6,
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
          fontSize: 13,
          color: colors.ink,
          lineHeight: 1.4,
        }}
      >
        {text.slice(0, charsVisible)}
        {showCursor ? <span style={{ color: colors.accent }}>▍</span> : null}
      </div>
    </div>
  );
};

export const RolloutsBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => (
  <div
    style={{
      opacity: useFadeIn(frame, enterAt - 4, 14),
      background: colors.surface,
      border: `1px solid ${colors.line}`,
      borderRadius: 10,
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: 6,
    }}
  >
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 9,
        letterSpacing: 1.6,
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
        gap: 5,
        flex: 1,
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

export const JudgesBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => {
  const workers = [
    { id: "judge-1", lines: ["→ rollout=cal_07", "← failed_grip", "  point=(403,312)"] },
    { id: "judge-2", lines: ["→ rollout=dep_14", "← missed_approach", "  point=null"] },
    { id: "judge-3", lines: ["→ rollout=cal_04", "← failed_grip", "  point=(957,1101)"] },
    { id: "judge-4", lines: ["→ rollout=dep_11", "← missed_approach", "  point=null"] },
  ];
  return (
    <div
      style={{
        opacity: useFadeIn(frame, enterAt - 4, 14),
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 10,
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: 1.6,
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
          gap: 5,
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
                borderRadius: 5,
                padding: "6px 8px",
                fontFamily: fonts.mono,
                fontSize: 8.5,
                color: "#a8c7fa",
                lineHeight: 1.4,
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
      <div
        style={{
          opacity: useFadeIn(frame, enterAt + workers.length * 6 + 8, 16),
          marginTop: 2,
          padding: "4px 8px",
          border: `1px dashed ${colors.phaseJudge}66`,
          borderRadius: 5,
          background: `${colors.phaseJudge}0a`,
          fontFamily: fonts.mono,
          fontSize: 8.5,
          color: colors.phaseJudge,
          letterSpacing: 1.0,
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
        border: `1px solid ${colors.phaseReport}80`,
        borderRadius: 10,
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        boxShadow: `0 0 0 3px ${colors.phaseReport}10`,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: 1.6,
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
              fontSize: l.weight ? 10 : 9,
              fontWeight: l.weight ?? 400,
              color: l.weight ? colors.ink : colors.ink3,
              lineHeight: 1.35,
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
  const tokenT = interpolate(
    frame,
    [activeAt - 4, activeAt + 14],
    [-0.2, 1.2],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  return (
    <div
      style={{
        position: "relative",
        height: "100%",
        opacity: op,
        display: "flex",
        alignItems: "center",
      }}
    >
      <div style={{ position: "relative", width: "100%", height: 24 }}>
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
    </div>
  );
};

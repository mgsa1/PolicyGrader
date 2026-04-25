import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";
import { PhaseCard } from "../components/PhaseCard";

// 10–20 s · The pipeline.
// Five phase cards animate in left-to-right with their artifacts.
// Highlight pulses run through after all cards have landed.

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

export const PipelineScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOp = useFadeIn(frame, 0, 18);
  const tagOp = useFadeIn(frame, 8, 18);
  const flowOp = useFadeIn(frame, 6 + PHASES.length * STAGGER, 16);

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
          The pipeline · 4 Managed-Agent sessions + 1 human phase
        </div>
        <div
          style={{
            marginTop: 16,
            fontSize: 56,
            fontWeight: 600,
            letterSpacing: -1,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          One English sentence in.
          <br />
          A measured eval{" "}
          <span style={{ color: colors.accent }}>out.</span>
        </div>
      </div>

      {/* Phase row */}
      <div
        style={{
          marginTop: 56,
          display: "flex",
          alignItems: "stretch",
          gap: 14,
        }}
      >
        {PHASES.map((p, i) => (
          <React.Fragment key={p.number}>
            <PhaseCard
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
          </React.Fragment>
        ))}
      </div>

      {/* Flow caption */}
      <div
        style={{
          marginTop: 36,
          opacity: flowOp,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingLeft: 4,
          paddingRight: 4,
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink3,
        }}
      >
        <span>plan</span>
        <span style={{ color: colors.line2 }}>──▶</span>
        <span>rollouts</span>
        <span style={{ color: colors.line2 }}>──▶</span>
        <span style={{ color: colors.phaseLabeling, fontWeight: 600 }}>
          human labels
        </span>
        <span style={{ color: colors.line2 }}>──▶</span>
        <span style={{ color: colors.phaseJudge, fontWeight: 600 }}>
          K judges in parallel
        </span>
        <span style={{ color: colors.line2 }}>──▶</span>
        <span>report</span>
      </div>

      <div
        style={{
          marginTop: 18,
          opacity: tagOp,
          fontSize: 18,
          color: colors.ink3,
          maxWidth: 1100,
          lineHeight: 1.45,
        }}
      >
        Sessions hand artifacts back to the host through{" "}
        <span style={{ fontFamily: fonts.mono, color: colors.ink }}>submit_*</span>{" "}
        custom tools. Every rollout, every label, every judgement is on disk —
        the dashboard is reproducible from the artifact tree.
      </div>
    </AbsoluteFill>
  );
};

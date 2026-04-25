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
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 1:55–2:20 · Why Opus 4.7.
// Persistent left rail with a check-stack that builds up as each capability
// is announced. Right side cycles through four visual beats, ~6 s each.
//
// Face PiP corner: lower-right (360x360). Each beat keeps its load-bearing
// content in the upper-left of the right column.

type Beat = {
  key: string;
  title: string;
  monoTag: string;
  description: string;
};

const BEATS: Beat[] = [
  {
    key: "vision",
    title: "2576-pixel vision + pointing",
    monoTag: "claude-opus-4-7 · vision",
    description:
      "The judge sees a 2-cm cube and points at the contact pixel. A coordinate — not a vibe.",
  },
  {
    key: "managed",
    title: "Managed Agents · K parallel sessions",
    monoTag: "managed-agents-2026-04-01",
    description:
      "Four roles, K judge workers, one orchestrator. Linear horizontal scaling.",
  },
  {
    key: "context",
    title: "1 M-token context · cluster in one pass",
    monoTag: "context_window = 1_000_000",
    description:
      "The reporter sees every finding in one shot — no embeddings, no stitching, just reasoning.",
  },
  {
    key: "memory",
    title: "/memories/ · file-based hand-off",
    monoTag: "submit_* · mirror_root/",
    description:
      "Agents think to disk. Every artifact replays the run on demand.",
  },
];

const BEAT_DUR = 6 * 30; // 6 s @ 30 fps

export const OpusMontageScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOp = useFadeIn(frame, 0, 16);

  // Active beat index.
  const beatIdx = Math.min(BEATS.length - 1, Math.floor(frame / BEAT_DUR));

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
          Why Opus 4.7
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 44,
            fontWeight: 600,
            letterSpacing: -0.8,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          Four capabilities.{" "}
          <span style={{ color: colors.accent }}>One pipeline only it can run.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        {/* LEFT rail: check stack */}
        <div
          style={{
            flex: 0.6,
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          {BEATS.map((b, i) => {
            const enterAt = i * BEAT_DUR + 4;
            const op = useFadeIn(frame, enterAt, 16);
            const isActive = beatIdx === i;
            const isDone = beatIdx > i;
            return (
              <div
                key={b.key}
                style={{
                  opacity: op,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "14px 16px",
                  borderRadius: 12,
                  background: isActive ? colors.surface : "transparent",
                  border: `1px solid ${isActive ? colors.accent : "transparent"}`,
                  boxShadow: isActive
                    ? `0 0 0 4px ${colors.accent}10`
                    : "none",
                  transition: "background 100ms",
                }}
              >
                <div
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: 999,
                    background: isActive || isDone ? colors.ok : colors.surface2,
                    display: "grid",
                    placeItems: "center",
                    color: isActive || isDone ? "#fff" : colors.ink3,
                    fontSize: 14,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  ✓
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 18,
                      fontWeight: 600,
                      color: colors.ink,
                      letterSpacing: -0.3,
                      lineHeight: 1.25,
                    }}
                  >
                    {b.title}
                  </div>
                  <div
                    style={{
                      marginTop: 4,
                      fontFamily: fonts.mono,
                      fontSize: 11,
                      color: colors.ink4,
                      letterSpacing: 0.4,
                    }}
                  >
                    {b.monoTag}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* RIGHT visual: cycles through the four beats. */}
        <div
          style={{
            flex: 1.4,
            position: "relative",
          }}
        >
          {BEATS.map((b, i) => {
            const start = i * BEAT_DUR;
            const end = start + BEAT_DUR;
            const op = interpolate(
              frame,
              [start, start + 8, end - 8, end],
              [0, 1, 1, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            );
            return (
              <div
                key={b.key}
                style={{
                  position: "absolute",
                  inset: 0,
                  opacity: op,
                  pointerEvents: "none",
                }}
              >
                <BeatVisual beat={b} frame={frame - start} />
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------- Beat visuals -------------------------------------------

const BeatVisual: React.FC<{ beat: Beat; frame: number }> = ({ beat, frame }) => {
  switch (beat.key) {
    case "vision":
      return <VisionBeat frame={frame} />;
    case "managed":
      return <ManagedBeat frame={frame} />;
    case "context":
      return <ContextBeat frame={frame} />;
    case "memory":
      return <MemoryBeat frame={frame} />;
    default:
      return null;
  }
};

// 2576-pixel vision with pointing — zoom into a keyframe with a red dot.
const VisionBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const zoom = interpolate(frame, [0, 60], [1.0, 1.18], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        borderRadius: 16,
        overflow: "hidden",
        background: colors.surface,
        border: `1px solid ${colors.line}`,
      }}
    >
      <Img
        src={staticFile("keyframes/dep_14.png")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom})`,
          transformOrigin: "55% 47%",
        }}
      />
      {/* Pixel coordinate readout */}
      <div
        style={{
          position: "absolute",
          left: 16,
          top: 16,
          fontFamily: fonts.mono,
          fontSize: 12,
          padding: "6px 10px",
          borderRadius: 8,
          background: "rgba(0,0,0,0.55)",
          color: "#fff",
        }}
      >
        2576 × 2576 px · point = (403, 312)
      </div>
      <div
        style={{
          position: "absolute",
          left: "55%",
          top: "47%",
          width: 18,
          height: 18,
          marginLeft: -9,
          marginTop: -9,
          borderRadius: 999,
          background: colors.err,
          boxShadow: `0 0 0 3px rgba(255,255,255,0.7), 0 0 24px ${colors.err}`,
        }}
      />
    </div>
  );
};

// 4 parallel session terminals with streaming dispatch lines.
const ManagedBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const sessions = ["planner", "rollout", "judge-1", "judge-2"];
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gridTemplateRows: "1fr 1fr",
        gap: 10,
      }}
    >
      {sessions.map((name, i) => (
        <SessionPane key={name} name={name} frame={frame} offset={i * 7} />
      ))}
    </div>
  );
};

const SessionPane: React.FC<{ name: string; frame: number; offset: number }> = ({
  name,
  frame,
  offset,
}) => {
  // Generate a few "dispatch" log lines that stream over time.
  const lines = [
    "→ session.start()",
    "  model = claude-opus-4-7",
    "→ tool_call: dispatch_rollout",
    "  rollout_id = cal_07",
    "→ tool_call: judge.frame_walk",
    "  frames = 18 · res = 1920",
    "← findings: failed_grip",
    "  point = (403, 312)",
    "→ submit_findings()",
    "  end_turn",
  ];
  const visibleCount = Math.max(0, Math.min(lines.length, Math.floor((frame - offset) / 6)));
  return (
    <div
      style={{
        background: "#0e1116",
        border: `1px solid ${colors.line}`,
        borderRadius: 10,
        padding: 14,
        fontFamily: fonts.mono,
        fontSize: 11,
        color: "#a8c7fa",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          fontSize: 10,
          color: "#6f7681",
          marginBottom: 8,
          letterSpacing: 1.4,
          textTransform: "uppercase",
        }}
      >
        ● session · {name}
      </div>
      {lines.slice(0, visibleCount).map((l, i) => (
        <div
          key={i}
          style={{
            color: l.startsWith("→")
              ? "#a8c7fa"
              : l.startsWith("←")
                ? "#137333"
                : "#9aa0a6",
            lineHeight: 1.45,
          }}
        >
          {l}
        </div>
      ))}
    </div>
  );
};

// 1M-context clustering — wall of jsonl lines collapses into 3 cluster cards.
const ContextBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const collapseT = interpolate(frame, [40, 100], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 16,
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 11,
          letterSpacing: 1.6,
          color: colors.ink4,
          textTransform: "uppercase",
        }}
      >
        findings.jsonl · 4 000 lines · 1 M-context input
      </div>

      <div style={{ flex: 1, position: "relative" }}>
        {/* Wall of fake jsonl lines that fade out as clusters appear */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            opacity: 1 - collapseT,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 4,
            fontFamily: fonts.mono,
            fontSize: 10,
            color: colors.ink4,
            overflow: "hidden",
            lineHeight: 1.4,
          }}
        >
          {Array.from({ length: 80 }).map((_, i) => (
            <div key={i} style={{ whiteSpace: "nowrap", overflow: "hidden" }}>
              {`{"id":"r_${String(i).padStart(4, "0")}","label":"${
                i % 3 === 0 ? "missed_approach" : i % 3 === 1 ? "failed_grip" : "missed_approach"
              }","point":${i % 4 === 0 ? "null" : `[${100 + i},${200 + i}]`}}`}
            </div>
          ))}
        </div>

        {/* Cluster cards reveal */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            opacity: collapseT,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 10,
          }}
        >
          {[
            { id: "C1", n: 1842, label: "missed_approach" },
            { id: "C2", n: 1108, label: "failed_grip" },
            { id: "C3", n: 1050, label: "abstain · point=null" },
          ].map((c) => (
            <div
              key={c.id}
              style={{
                padding: "14px 18px",
                borderRadius: 12,
                background: colors.bg,
                border: `1px solid ${colors.line}`,
                display: "flex",
                alignItems: "center",
                gap: 14,
                fontFamily: fonts.mono,
                fontSize: 14,
              }}
            >
              <span style={{ color: colors.ink4, fontSize: 11, letterSpacing: 1.4 }}>
                {c.id}
              </span>
              <span style={{ color: colors.ink, fontWeight: 600 }}>
                {c.n.toLocaleString()}
              </span>
              <span style={{ color: colors.ink3 }}>{c.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// /memories/ tree filling up as agents hand off.
const MemoryBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const lines = [
    { depth: 0, name: "/memories/", at: 0, color: colors.ink3 },
    { depth: 1, name: "plan.md", at: 8, color: colors.phasePlanner },
    { depth: 1, name: "test_matrix.csv", at: 14, color: colors.phasePlanner },
    { depth: 1, name: "rollouts/", at: 22, color: colors.phaseRollout },
    { depth: 2, name: "cal_00.mp4", at: 28, color: colors.phaseRollout },
    { depth: 2, name: "cal_01.mp4", at: 32, color: colors.phaseRollout },
    { depth: 2, name: "dep_14.mp4", at: 38, color: colors.phaseRollout },
    { depth: 1, name: "human_labels.jsonl", at: 48, color: colors.phaseLabeling },
    { depth: 1, name: "findings.jsonl", at: 60, color: colors.phaseJudge },
    { depth: 1, name: "report.md", at: 80, color: colors.phaseReport },
  ];

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "#0e1116",
        border: `1px solid ${colors.line}`,
        borderRadius: 16,
        padding: 22,
        fontFamily: fonts.mono,
        fontSize: 14,
        color: "#a8c7fa",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          fontSize: 11,
          letterSpacing: 1.6,
          color: "#6f7681",
          textTransform: "uppercase",
          marginBottom: 14,
        }}
      >
        ● mirror_root · artifact tree
      </div>

      {lines.map((l) => {
        const op = interpolate(frame, [l.at - 4, l.at + 8], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={l.name}
            style={{
              opacity: op,
              paddingLeft: l.depth * 22,
              lineHeight: 1.7,
              color: l.depth === 0 ? "#9aa0a6" : "#fff",
            }}
          >
            <span style={{ color: l.color }}>↳</span>{" "}
            <span style={{ color: l.depth === 0 ? "#9aa0a6" : "#e8eaed" }}>
              {l.name}
            </span>
          </div>
        );
      })}
    </div>
  );
};

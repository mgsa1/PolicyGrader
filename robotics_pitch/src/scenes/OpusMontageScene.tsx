import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  Img,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// Why Opus 4.7 + Managed Agents.
// Persistent left rail with a check-stack that builds up as each capability
// is announced. Right side cycles through three visual beats, 5 s each
// (15 s total — Hero.tsx Sequence is 15 s long).
//
// The point-abstention + telemetry engineering story has its own scene
// (JudgeChallengesScene, sequenced just before this one) — this scene
// stays focused on the three capabilities that make the pipeline run.
//
// Face PiP corner: lower-right (360x360). Each beat keeps its load-bearing
// content in the upper-left of the right column.

type Beat = {
  key: string;
  title: string;
  monoTag: string;
  description: string;
  dur: number; // frames
};

const BEATS: Beat[] = [
  {
    key: "vision",
    title: "2576-pixel vision + pointing",
    monoTag: "claude-opus-4-7 · vision",
    description:
      "The judge sees a 2-cm cube and points at the contact pixel. A coordinate — not a vibe.",
    dur: 5 * 30,
  },
  {
    key: "managed",
    title: "Managed Agents · K parallel sessions",
    monoTag: "managed-agents-2026-04-01",
    description:
      "Four roles, K judge workers, one orchestrator. Linear horizontal scaling.",
    dur: 5 * 30,
  },
  {
    key: "context",
    title: "1 M-token context · cluster in one pass",
    monoTag: "context_window = 1_000_000",
    description:
      "The reporter sees every finding in one shot — no embeddings, no stitching, just reasoning.",
    dur: 5 * 30,
  },
];

// Cumulative start frame for each beat — derived from per-beat durations.
const BEAT_STARTS: number[] = (() => {
  const starts: number[] = [];
  let cum = 0;
  for (const b of BEATS) {
    starts.push(cum);
    cum += b.dur;
  }
  return starts;
})();

export const OpusMontageScene: React.FC = () => {
  const frame = useCurrentFrame();

  const headerOp = useFadeIn(frame, 0, 16);

  // Active beat index — last beat whose start frame we've reached.
  const beatIdx = (() => {
    for (let i = BEATS.length - 1; i >= 0; i--) {
      if (frame >= BEAT_STARTS[i]) return i;
    }
    return 0;
  })();

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
          Why Opus 4.7 + Managed Agents
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 40,
            fontWeight: 600,
            letterSpacing: -0.8,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          Three capabilities.{" "}
          <span style={{ color: colors.accent }}>
            Uniquely enabled by Opus 4.7 and Claude Managed Agents.
          </span>
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
            const enterAt = BEAT_STARTS[i] + 4;
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
            const start = BEAT_STARTS[i];
            const end = start + b.dur;
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
    default:
      return null;
  }
};

// 2576-pixel vision with pointing — zoom into a keyframe with a red dot.
// The dot anchor (DOT_X / DOT_Y) is the gripper-cube contact pixel on
// dep_31.png; zoom origin shares the same anchor so the push-in lands
// on the contact, not on the robot's body.
const DOT_X_PCT = 50;
const DOT_Y_PCT = 58;
const VisionBeat: React.FC<{ frame: number }> = ({ frame }) => {
  const zoom = interpolate(frame, [0, 60], [1.0, 1.35], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  // Caption shows the same anchor in 2576-px coords so it tracks the dot.
  const pointX = Math.round((DOT_X_PCT / 100) * 2576);
  const pointY = Math.round((DOT_Y_PCT / 100) * 2576);
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
        src={staticFile("keyframes/dep_31.png")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom})`,
          transformOrigin: `${DOT_X_PCT}% ${DOT_Y_PCT}%`,
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
        2576 × 2576 px · point = ({pointX}, {pointY})
      </div>
      <div
        style={{
          position: "absolute",
          left: `${DOT_X_PCT}%`,
          top: `${DOT_Y_PCT}%`,
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
    "  point = (1262, 1546)",
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


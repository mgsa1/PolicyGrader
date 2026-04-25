import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  spring,
} from "remotion";
import { colors, fonts, numbers } from "../theme";
import { useFadeIn } from "../components/easing";

// 0:33–0:48 · Name reveal.
//
//   Beat A (0–10 s): centered title block — PolicyGrader · tagline ·
//                    "Powered by Claude Opus 4.7 and Claude Managed Agents".
//                    Nothing else on screen. Vertically + horizontally centered.
//   Beat B (10–15 s): the "This run vs manual review" 6-cell dashboard
//                    slides up from the bottom of the viewport. The title
//                    nudges up to share the screen.

const formatCost = (usd: number) => `$${usd.toFixed(2)}`;
const formatDuration = (seconds: number) => {
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
};

// Hardcoded for the dashboard reveal — illustration scenario:
//   2 830 scenarios = 50 cal + 2 780 dep
//   pipeline wall time = 50 min · manual baseline still 71 h
const DASHBOARD = {
  scenarios: 2830,
  scenariosCal: 50,
  scenariosDep: 2780,
  pipelineSeconds: 50 * 60, // 50 min → "50m 0s"
  manualSeconds: 71 * 3600,
  timeDeltaPct: -99,
};

export const NameRevealScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // --- Beat A: centered title -------------------------------------------
  const eyebrowOp = useFadeIn(frame, 6, 18);
  const titleOp = useFadeIn(frame, 14, 22);
  const titleScale = spring({
    frame: frame - 14,
    fps,
    config: { damping: 18, stiffness: 160, mass: 0.7 },
  });
  const taglineOp = useFadeIn(frame, 36, 22);
  const poweredOp = useFadeIn(frame, 56, 22);

  // --- Beat B: dashboard slides in at the very end ----------------------
  const dashEnter = 10 * fps; // dashboard begins entering at 10 s
  const dashT = interpolate(frame, [dashEnter, dashEnter + 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  const dashTranslateY = (1 - dashT) * 110; // %, slides up from below

  // Title nudges up a touch when the dashboard arrives.
  const titleNudgeY = -dashT * 70;

  return (
    <AbsoluteFill style={{ position: "relative" }}>
      {/* Beat A: centered title block */}
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "0 96px",
          transform: `translateY(${titleNudgeY}px)`,
        }}
      >
        <div
          style={{
            opacity: eyebrowOp,
            fontFamily: fonts.mono,
            fontSize: 13,
            letterSpacing: 2.8,
            color: colors.ink4,
            textTransform: "uppercase",
            display: "inline-flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: colors.accent,
              boxShadow: `0 0 12px ${colors.accent}`,
            }}
          />
          Introducing
        </div>

        <div
          style={{
            marginTop: 22,
            opacity: titleOp,
            transform: `scale(${0.96 + titleScale * 0.04})`,
            fontSize: 168,
            fontWeight: 700,
            lineHeight: 0.95,
            letterSpacing: -4.4,
            color: colors.ink,
          }}
        >
          Policy<span style={{ color: colors.accent }}>Grader</span>
          <span style={{ color: colors.ink3, fontWeight: 500 }}>.</span>
        </div>

        <div
          style={{
            opacity: taglineOp,
            marginTop: 28,
            fontSize: 36,
            color: colors.ink2,
            lineHeight: 1.3,
            letterSpacing: -0.4,
          }}
        >
          <span style={{ fontWeight: 600, color: colors.ink }}>
            One prompt in.
          </span>{" "}
          <span style={{ color: colors.ink3 }}>A full control policy stress test out.</span>
        </div>

        <div
          style={{
            opacity: poweredOp,
            marginTop: 18,
            fontFamily: fonts.mono,
            fontSize: 16,
            letterSpacing: 0.4,
            color: colors.ink4,
          }}
        >
          Powered by{" "}
          <span style={{ color: colors.ink2, fontWeight: 600 }}>
            Claude Opus 4.7
          </span>{" "}
          and{" "}
          <span style={{ color: colors.ink2, fontWeight: 600 }}>
            Claude Managed Agents
          </span>
        </div>
      </AbsoluteFill>

      {/* Beat B: dashboard slides up from the bottom edge */}
      <div
        style={{
          position: "absolute",
          left: 64,
          right: 64,
          bottom: 32,
          transform: `translateY(${dashTranslateY}%)`,
          opacity: dashT,
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.6,
            color: colors.ink4,
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          This run vs manual review
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(6, 1fr)",
            gap: 10,
          }}
        >
          <MetricCell
            label="Cost"
            value={formatCost(numbers.pipelineCostUsd)}
            baseline={formatCost(numbers.manualCostUsd)}
            deltaPct={numbers.costDeltaPct}
          />
          <MetricCell
            label="Wall time"
            value={formatDuration(DASHBOARD.pipelineSeconds)}
            baseline={formatDuration(DASHBOARD.manualSeconds)}
            deltaPct={DASHBOARD.timeDeltaPct}
          />
          <MetricCell
            label="Scenarios"
            value={DASHBOARD.scenarios.toLocaleString()}
            cohortSub={{ cal: DASHBOARD.scenariosCal, dep: DASHBOARD.scenariosDep }}
          />
          <MetricCell
            label="Label accuracy"
            value={`${numbers.precisionPct}%`}
            sub={`CI ${numbers.precisionCiLow}–${numbers.precisionCiHigh}`}
          />
          <MetricCell
            label="Avg recall"
            value={`${numbers.recallPct}%`}
            sub={`CI ${numbers.recallCiLow}–${numbers.recallCiHigh}`}
          />
          <MetricCell
            label="Clusters"
            value={numbers.clusters.toLocaleString()}
            sub="from 1 M ctx"
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---- MetricCell — mirrors .pg-metric-cell from chrome.py::_hero_right ----

type MetricCellProps = {
  label: string;
  value: string;
  baseline?: string;
  deltaPct?: number;
  cohortSub?: { cal: number; dep: number };
  sub?: string;
};

const MetricCell: React.FC<MetricCellProps> = ({
  label,
  value,
  baseline,
  deltaPct,
  cohortSub,
  sub,
}) => (
  <div
    style={{
      background: colors.surface,
      border: `1px solid ${colors.line}`,
      borderRadius: 12,
      padding: "14px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 6,
      boxShadow: "0 4px 14px rgba(31,31,31,0.04)",
    }}
  >
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 10,
        letterSpacing: 1.6,
        color: colors.ink4,
        textTransform: "uppercase",
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontSize: 28,
        fontWeight: 600,
        color: colors.ink,
        letterSpacing: -0.6,
        lineHeight: 1,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {value}
    </div>
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 11,
        color: colors.ink4,
        display: "flex",
        gap: 6,
        alignItems: "baseline",
      }}
    >
      {baseline ? (
        <>
          <s>{baseline}</s>
          {deltaPct !== undefined ? (
            <span style={{ color: colors.ok, fontWeight: 600 }}>
              {deltaPct > 0 ? "+" : ""}
              {deltaPct}%
            </span>
          ) : null}
        </>
      ) : cohortSub ? (
        <>
          <span style={{ color: colors.cal, fontWeight: 600 }}>
            {cohortSub.cal.toLocaleString()} cal
          </span>
          <span>·</span>
          <span style={{ color: colors.dep, fontWeight: 600 }}>
            {cohortSub.dep.toLocaleString()} dep
          </span>
        </>
      ) : (
        sub
      )}
    </div>
  </div>
);

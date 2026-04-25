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

// 0:33–0:48 · Name reveal + value + comparison panel.
//
//   Beat A (0–7 s): "PolicyGrader." big, with the "One prompt in / measured
//                   eval out" tagline + "Powered by Claude Opus 4.7 and
//                   Claude Managed Agents" sub.
//   Beat B (7–15 s): the absolute key value prop — the run-level hero's
//                   "This run vs manual review" 6-cell metric grid from
//                   src/ui/panes/chrome.py::_hero_right:
//                     Cost / Wall time / Scenarios /
//                     Label accuracy / Avg recall / Clusters
//                   Cost & Wall time carry strikethrough baselines and a
//                   delta percentage; Scenarios shows the cohort split with
//                   the cal/dep colors.

// Mirror format_cost ("$X.XX") and format_duration ("Hh Mm Ss").
const formatCost = (usd: number) => `$${usd.toFixed(2)}`;
const formatDuration = (seconds: number) => {
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${h}h ${m}m ${s}s` : `${m}m ${s}s`;
};

const PIPELINE_SECONDS = numbers.pipelineHours * 3600;
const MANUAL_SECONDS = numbers.manualHours * 3600;
const TIME_SAVED_SECONDS = MANUAL_SECONDS - PIPELINE_SECONDS;

export const NameRevealScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Beat A — title card.
  const eyebrowOp = useFadeIn(frame, 6, 18);
  const titleOp = useFadeIn(frame, 14, 22);
  const titleScale = spring({
    frame: frame - 14,
    fps,
    config: { damping: 18, stiffness: 160, mass: 0.7 },
  });
  const taglineOp = useFadeIn(frame, 32, 22);
  const poweredOp = useFadeIn(frame, 50, 22);

  // Beat B — Overview KPI strip slides up.
  const kpiEnter = 7 * fps;
  const kpiEyebrowOp = useFadeIn(frame, kpiEnter, 14);
  const kpiOp = useFadeIn(frame, kpiEnter + 6, 18);
  const kpiY = interpolate(
    frame,
    [kpiEnter + 6, kpiEnter + 28],
    [40, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  // Title card drifts up + dims slightly when KPI enters.
  const titleDrift = interpolate(
    frame,
    [kpiEnter - 4, kpiEnter + 18],
    [0, -28],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );
  const titleFade = interpolate(
    frame,
    [kpiEnter - 4, kpiEnter + 18],
    [1, 0.65],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill
      style={{
        paddingTop: 132,
        paddingLeft: 96,
        paddingRight: 96,
        display: "flex",
        flexDirection: "column",
        gap: 24,
      }}
    >
      {/* Beat A: title card */}
      <div
        style={{
          opacity: titleFade,
          transform: `translateY(${titleDrift}px)`,
          maxWidth: 1280,
        }}
      >
        <div
          style={{
            opacity: eyebrowOp,
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
              background: colors.accent,
              boxShadow: `0 0 12px ${colors.accent}`,
            }}
          />
          Introducing
        </div>

        <div
          style={{
            marginTop: 14,
            opacity: titleOp,
            transform: `scale(${0.96 + titleScale * 0.04})`,
            transformOrigin: "left center",
            fontSize: 124,
            fontWeight: 700,
            lineHeight: 0.96,
            letterSpacing: -3.4,
            color: colors.ink,
          }}
        >
          Policy<span style={{ color: colors.accent }}>Grader</span>
          <span style={{ color: colors.ink3, fontWeight: 500 }}>.</span>
        </div>

        <div
          style={{
            opacity: taglineOp,
            marginTop: 18,
            fontSize: 30,
            color: colors.ink2,
            lineHeight: 1.3,
            letterSpacing: -0.4,
          }}
        >
          <span style={{ fontWeight: 600, color: colors.ink }}>
            One prompt in.
          </span>{" "}
          <span style={{ color: colors.ink3 }}>A measured eval out.</span>
        </div>

        <div
          style={{
            opacity: poweredOp,
            marginTop: 12,
            fontFamily: fonts.mono,
            fontSize: 14,
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
      </div>

      {/* Beat B: "This run vs manual review" — the absolute key value prop */}
      <div
        style={{
          marginTop: 8,
          opacity: kpiOp,
          transform: `translateY(${kpiY}px)`,
        }}
      >
        {/* Eyebrow — mirrors .pg-hero-right-eyebrow in chrome.py */}
        <div
          style={{
            opacity: kpiEyebrowOp,
            marginBottom: 16,
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.6,
            color: colors.ink4,
            textTransform: "uppercase",
          }}
        >
          This run vs manual review
        </div>

        {/* 6-cell metric grid — 3 cols × 2 rows. Mirrors .pg-metric-grid. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 12,
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
            value={formatDuration(PIPELINE_SECONDS)}
            baseline={formatDuration(MANUAL_SECONDS)}
            deltaPct={numbers.timeDeltaPct}
          />
          <MetricCell
            label="Scenarios"
            value={numbers.scenarios.toLocaleString()}
            cohortSub={{ cal: numbers.scenariosCal, dep: numbers.scenariosDep }}
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
  // Cost / Wall time variants get strikethrough baseline + signed delta.
  baseline?: string;
  deltaPct?: number;
  // Scenarios variant gets a cohort split.
  cohortSub?: { cal: number; dep: number };
  // Other variants get a plain mono sub line.
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
      borderRadius: 14,
      padding: "18px 20px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      boxShadow: "0 4px 14px rgba(31,31,31,0.04)",
    }}
  >
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 11,
        letterSpacing: 1.8,
        color: colors.ink4,
        textTransform: "uppercase",
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontSize: 38,
        fontWeight: 600,
        color: colors.ink,
        letterSpacing: -0.8,
        lineHeight: 1,
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {value}
    </div>
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 12,
        color: colors.ink4,
        display: "flex",
        gap: 8,
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

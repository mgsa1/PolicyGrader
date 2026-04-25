import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts, numbers } from "../theme";
import { useFadeIn } from "../components/easing";

// 34–40 s · The numbers.
// Layout matches the live dashboard "This run vs manual review" panel:
//   3×2 stat grid (cost / wall / scenarios | precision / recall / clusters)
// + a big green "Saved" hero card below.

const usd = (n: number) =>
  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

const useCount = (
  frame: number,
  start: number,
  to: number,
  duration = 26,
): number => {
  const t = interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  return to * t;
};

interface CellProps {
  label: string;
  value: React.ReactNode;
  sub: React.ReactNode;
  enterAt: number;
  rightBorder?: boolean;
  bottomBorder?: boolean;
}

const Cell: React.FC<CellProps> = ({
  label,
  value,
  sub,
  enterAt,
  rightBorder,
  bottomBorder,
}) => {
  const frame = useCurrentFrame();
  const op = useFadeIn(frame, enterAt, 12);
  const slideY = interpolate(
    frame,
    [enterAt, enterAt + 18],
    [12, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );

  return (
    <div
      style={{
        padding: "20px 24px 22px",
        opacity: op,
        transform: `translateY(${slideY}px)`,
        borderRight: rightBorder ? `1px solid ${colors.line}` : "none",
        borderBottom: bottomBorder ? `1px solid ${colors.line}` : "none",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minHeight: 130,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 11,
          letterSpacing: 2.2,
          color: colors.ink4,
          textTransform: "uppercase",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 48,
          fontWeight: 600,
          letterSpacing: -1,
          color: colors.ink,
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
          marginTop: 2,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {sub}
      </div>
    </div>
  );
};

export const NumbersScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOp = useFadeIn(frame, 0, 14);
  const panelOp = useFadeIn(frame, 4, 18);

  // Counters
  const cost = useCount(frame, 8, numbers.pipelineCostUsd, 28);
  const hours = useCount(frame, 14, numbers.pipelineHours, 28);
  const scens = useCount(frame, 20, numbers.scenarios, 28);
  const precision = useCount(frame, 38, numbers.precisionPct, 24);
  const recall = useCount(frame, 44, numbers.recallPct, 24);
  const clusters = useCount(frame, 50, numbers.clusters, 18);

  const savedOp = useFadeIn(frame, 72, 16);
  const savedSlide = interpolate(
    frame,
    [72, 96],
    [16, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.bezier(0.22, 1, 0.36, 1),
    },
  );
  const saved = useCount(frame, 76, numbers.savedUsd, 36);

  const closingOp = useFadeIn(frame, 116, 22);

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
          This sweep vs manual review
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
          From{" "}
          <span style={{ color: colors.err, textDecoration: "line-through" }}>
            five working weeks
          </span>{" "}
          to{" "}
          <span style={{ color: colors.ok }}>two days.</span>
        </div>
      </div>

      {/* 3×2 dashboard panel */}
      <div
        style={{
          background: colors.surface,
          border: `1px solid ${colors.line}`,
          borderRadius: 18,
          opacity: panelOp,
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          overflow: "hidden",
          boxShadow: "0 6px 20px rgba(31,31,31,0.04)",
        }}
      >
        <Cell
          label="Cost"
          value={usd(cost)}
          sub={
            <span>
              <span style={{ textDecoration: "line-through" }}>
                {usd(numbers.manualCostUsd)}
              </span>{" "}
              <span style={{ color: colors.ok, fontWeight: 600 }}>
                {numbers.costDeltaPct}%
              </span>
            </span>
          }
          enterAt={6}
          rightBorder
          bottomBorder
        />
        <Cell
          label="Wall time"
          value={`${Math.round(hours)} h`}
          sub={
            <span>
              <span style={{ textDecoration: "line-through" }}>
                {numbers.manualHours} h
              </span>{" "}
              <span style={{ color: colors.ok, fontWeight: 600 }}>
                {numbers.timeDeltaPct}%
              </span>
            </span>
          }
          enterAt={12}
          rightBorder
          bottomBorder
        />
        <Cell
          label="Scenarios"
          value={Math.round(scens).toLocaleString()}
          sub={`${numbers.scenariosCal.toLocaleString()} cal · ${numbers.scenariosDep.toLocaleString()} dep`}
          enterAt={18}
          bottomBorder
        />
        <Cell
          label="Precision"
          value={
            <span>
              {Math.round(precision)}
              <span style={{ fontSize: 24, color: colors.ink3 }}>%</span>
            </span>
          }
          sub={`CI ${numbers.precisionCiLow} – ${numbers.precisionCiHigh}`}
          enterAt={36}
          rightBorder
        />
        <Cell
          label="Recall"
          value={
            <span>
              {Math.round(recall)}
              <span style={{ fontSize: 24, color: colors.ink3 }}>%</span>
            </span>
          }
          sub={`CI ${numbers.recallCiLow} – ${numbers.recallCiHigh}`}
          enterAt={42}
          rightBorder
        />
        <Cell
          label="Clusters"
          value={Math.round(clusters).toLocaleString()}
          sub="from 1M ctx"
          enterAt={48}
        />
      </div>

      {/* Big "Saved" hero card */}
      <div
        style={{
          opacity: savedOp,
          transform: `translateY(${savedSlide}px)`,
          background: colors.surface,
          border: `1px solid ${colors.ok}`,
          borderRadius: 18,
          boxShadow: `0 0 0 4px ${colors.ok}1A, 0 24px 60px rgba(31,31,31,0.10)`,
          padding: "28px 36px",
          display: "flex",
          alignItems: "center",
          gap: 32,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              letterSpacing: 2.2,
              color: colors.ink4,
              textTransform: "uppercase",
            }}
          >
            Saved per pre-deployment sweep
          </div>
          <div
            style={{
              fontSize: 80,
              fontWeight: 600,
              letterSpacing: -1.4,
              color: colors.ok,
              lineHeight: 1,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {usd(saved)}
          </div>
        </div>
      </div>

      {/* Closing tagline */}
      <div
        style={{
          opacity: closingOp,
          textAlign: "center",
          fontSize: 20,
          fontWeight: 500,
          color: colors.ink2,
          marginTop: -4,
        }}
      >
        Robot policy evals —{" "}
        <span style={{ color: colors.accent, fontWeight: 600 }}>
          hours to minutes.
        </span>{" "}
        And it tells you when to trust the judge.
      </div>
    </AbsoluteFill>
  );
};

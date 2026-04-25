import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts, numbers } from "../theme";
import { useFadeIn } from "../components/easing";

// 34–40 s · The numbers.
// Cost / time / scenarios. The "saved" number reveals last and is the hero.

const usd = (n: number) =>
  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

const useCount = (
  frame: number,
  start: number,
  to: number,
  duration = 30,
): number => {
  const t = interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  return to * t;
};

const Stat: React.FC<{
  label: string;
  value: string;
  baseline?: string;
  enterAt: number;
  color?: string;
  big?: boolean;
}> = ({ label, value, baseline, enterAt, color = colors.ink, big = false }) => {
  const frame = useCurrentFrame();
  const op = useFadeIn(frame, enterAt, 14);
  const slideY = interpolate(
    frame,
    [enterAt, enterAt + 22],
    [18, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  return (
    <div
      style={{
        opacity: op,
        transform: `translateY(${slideY}px)`,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 18,
        padding: big ? "32px 36px" : "26px 28px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        boxShadow: big
          ? `0 0 0 4px ${colors.ok}1A, 0 30px 70px rgba(31,31,31,0.10)`
          : "0 6px 20px rgba(31,31,31,0.04)",
        borderColor: big ? colors.ok : colors.line,
        flex: big ? "0 0 auto" : 1,
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
          fontSize: big ? 96 : 56,
          fontWeight: 600,
          letterSpacing: -1.2,
          color,
          lineHeight: 1,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {baseline ? (
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 13,
            color: colors.ink4,
            marginTop: 2,
          }}
        >
          <span style={{ textDecoration: "line-through" }}>{baseline}</span>{" "}
          <span style={{ color: colors.ok }}>baseline</span>
        </div>
      ) : null}
    </div>
  );
};

export const NumbersScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOp = useFadeIn(frame, 0, 16);

  const cost = useCount(frame, 8, numbers.pipelineCostUsd, 30);
  const hours = useCount(frame, 14, numbers.pipelineHours, 30);
  const scens = useCount(frame, 20, numbers.scenarios, 30);
  const saved = useCount(frame, 36, numbers.savedUsd, 36);

  const closingOp = useFadeIn(frame, 110, 22);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 124,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "column",
        gap: 30,
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
          Headline · 4 000-rollout pre-deployment sweep
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

      {/* Three small stats */}
      <div style={{ display: "flex", gap: 20 }}>
        <Stat
          label="Pipeline cost"
          value={usd(cost)}
          baseline={usd(numbers.manualCostUsd)}
          enterAt={6}
        />
        <Stat
          label="Wall time"
          value={`${Math.round(hours)} h`}
          baseline={`${numbers.manualHours} h`}
          enterAt={12}
        />
        <Stat
          label="Scenarios"
          value={Math.round(scens).toLocaleString()}
          enterAt={18}
        />
      </div>

      {/* Big savings reveal */}
      <Stat
        label="Saved per pre-deployment sweep"
        value={usd(saved)}
        enterAt={32}
        color={colors.ok}
        big
      />

      <div
        style={{
          opacity: closingOp,
          textAlign: "center",
          fontSize: 22,
          fontWeight: 500,
          color: colors.ink2,
          marginTop: 4,
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

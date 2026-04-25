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

// 2:20–2:30 · CLOSE.
// Side-by-side counter: manual review baseline (left, dimmed/crossed) vs
// PolicyGrader actual (right, hero green). Then a dark slate covers the
// scene and the final card reads:
//   "PolicyGrader — eval the policy. Grade the grader."

const usd = (n: number) =>
  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

const pctDrop = (baseline: number, actual: number) =>
  `−${Math.round((1 - actual / baseline) * 100)}%`;

export const CloseScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Beat A: side-by-side reveal (0–4 s)
  const eyebrowOp = useFadeIn(frame, 0, 14);
  const leftOp = useFadeIn(frame, 6, 18);
  const rightOp = useFadeIn(frame, 18, 18);

  // Beat B: dark slate washes in (5 s — 7 s)
  const slateAt = 5 * fps;
  const slateOp = interpolate(
    frame,
    [slateAt, slateAt + 18],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  // Beat C: final card text (6.5 s+)
  const finalAt = Math.round(6.5 * fps);
  const finalOp = useFadeIn(frame, finalAt, 18);
  const finalScale = spring({
    frame: frame - finalAt,
    fps,
    config: { damping: 18, stiffness: 160, mass: 0.7 },
  });

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
      {/* Side-by-side counter */}
      <div style={{ opacity: eyebrowOp }}>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.6,
            color: colors.ink4,
            textTransform: "uppercase",
          }}
        >
          The math · 4 000-rollout pre-deployment sweep
        </div>
        <div
          style={{
            marginTop: 14,
            fontSize: 38,
            fontWeight: 600,
            letterSpacing: -0.6,
            color: colors.ink,
            lineHeight: 1.05,
          }}
        >
          Weeks of human review.{" "}
          <span style={{ color: colors.accent }}>Compressed to minutes.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 28, alignItems: "stretch", flex: 1 }}>
        {/* LEFT: manual baseline */}
        <Side
          variant="baseline"
          opacity={leftOp}
          eyebrow="Manual review"
          cost={usd(numbers.manualCostUsd)}
          time={`${numbers.manualHours} h`}
          tail="engineer-watching-videos"
        />

        {/* Arrow */}
        <div
          style={{
            display: "grid",
            placeItems: "center",
            opacity: rightOp,
          }}
        >
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 32,
              color: colors.ink3,
            }}
          >
            ──▶
          </div>
        </div>

        {/* RIGHT: PolicyGrader */}
        <Side
          variant="hero"
          opacity={rightOp}
          eyebrow="PolicyGrader"
          cost={usd(numbers.pipelineCostUsd)}
          time={`${numbers.pipelineMinutes} min`}
          costDelta={pctDrop(numbers.manualCostUsd, numbers.pipelineCostUsd)}
          timeDelta={pctDrop(numbers.manualHours * 60, numbers.pipelineMinutes)}
          tail="audited by the same model that did the work"
        />
      </div>

      {/* Dark slate */}
      <AbsoluteFill
        style={{
          opacity: slateOp,
          background:
            "linear-gradient(180deg, rgba(15,18,24,0.0) 0%, rgba(15,18,24,1) 60%)",
          pointerEvents: "none",
        }}
      />

      {/* Final card text on the dark slate */}
      <AbsoluteFill
        style={{
          opacity: slateOp,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: 18,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            opacity: finalOp,
            transform: `scale(${0.96 + finalScale * 0.04})`,
            fontFamily: fonts.sans,
            fontWeight: 700,
            fontSize: 92,
            letterSpacing: -2.4,
            color: "#fff",
            textAlign: "center",
            lineHeight: 1.0,
          }}
        >
          Policy<span style={{ color: "#79b8ff" }}>Grader</span>
        </div>

        <div
          style={{
            opacity: finalOp,
            fontFamily: fonts.sans,
            fontSize: 26,
            color: "rgba(255,255,255,0.78)",
            letterSpacing: -0.2,
            textAlign: "center",
          }}
        >
          One prompt in.{" "}
          <span style={{ color: "#fff", fontWeight: 600 }}>
            A full control policy stress test out.
          </span>
        </div>

        <div
          style={{
            opacity: finalOp,
            marginTop: 18,
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2.4,
            color: "rgba(255,255,255,0.45)",
            textTransform: "uppercase",
          }}
        >
          Powered by Claude Opus 4.7 and Claude Managed Agents
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const DeltaPill: React.FC<{ label: string }> = ({ label }) => (
  <div
    style={{
      marginTop: 12,
      display: "inline-block",
      padding: "4px 10px",
      borderRadius: 999,
      fontFamily: fonts.mono,
      fontSize: 12,
      fontWeight: 600,
      letterSpacing: 0.4,
      color: colors.ok,
      background: `${colors.ok}1A`,
      border: `1px solid ${colors.ok}55`,
    }}
  >
    {label} vs manual
  </div>
);

const Side: React.FC<{
  variant: "baseline" | "hero";
  opacity: number;
  eyebrow: string;
  cost: string;
  time: string;
  costDelta?: string;
  timeDelta?: string;
  tail: string;
}> = ({ variant, opacity, eyebrow, cost, time, costDelta, timeDelta, tail }) => {
  const isHero = variant === "hero";
  return (
    <div
      style={{
        flex: 1,
        opacity,
        background: colors.surface,
        border: `1px solid ${isHero ? colors.ok : colors.line}`,
        borderRadius: 18,
        padding: "30px 36px",
        display: "flex",
        flexDirection: "column",
        gap: 18,
        boxShadow: isHero
          ? `0 0 0 4px ${colors.ok}1A, 0 24px 60px rgba(31,31,31,0.10)`
          : "0 6px 20px rgba(31,31,31,0.04)",
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          letterSpacing: 2.4,
          color: isHero ? colors.ok : colors.ink4,
          textTransform: "uppercase",
          fontWeight: 600,
        }}
      >
        ● {eyebrow}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 28,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              color: colors.ink4,
              letterSpacing: 1.6,
              textTransform: "uppercase",
            }}
          >
            Cost
          </div>
          <div
            style={{
              fontSize: 64,
              fontWeight: 600,
              letterSpacing: -1.4,
              color: isHero ? colors.ok : colors.err,
              textDecoration: isHero ? undefined : "line-through",
              lineHeight: 1,
              marginTop: 4,
            }}
          >
            {cost}
          </div>
          {isHero && costDelta ? <DeltaPill label={costDelta} /> : null}
        </div>
        <div>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              color: colors.ink4,
              letterSpacing: 1.6,
              textTransform: "uppercase",
            }}
          >
            Time
          </div>
          <div
            style={{
              fontSize: 64,
              fontWeight: 600,
              letterSpacing: -1.4,
              color: isHero ? colors.ok : colors.err,
              textDecoration: isHero ? undefined : "line-through",
              lineHeight: 1,
              marginTop: 4,
            }}
          >
            {time}
          </div>
          {isHero && timeDelta ? <DeltaPill label={timeDelta} /> : null}
        </div>
      </div>

      <div
        style={{
          marginTop: "auto",
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink3,
          paddingTop: 14,
          borderTop: `1px dashed ${colors.line2}`,
        }}
      >
        ↳ {tail}
      </div>
    </div>
  );
};

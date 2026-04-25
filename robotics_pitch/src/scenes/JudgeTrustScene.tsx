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

// 1:40–1:55 · HERO SHOT.
// "PolicyGrader doesn't just grade the robot. It grades the grader."
//
// Beat A (0–4 s): a 2×2 confusion matrix populates with per-label P/R numbers
//                 from human labels ⋈ findings on the calibration cohort.
// Beat B (4–8 s): the precision value lifts off the matrix and flies
//                 to the right half of the screen.
// Beat C (8–13 s): four deployment cluster cards are revealed; the chips
//                  land on them as Judge-Trust badges.
// Beat D (13–15 s): "It grades the grader." closes out at the bottom.
//
// Numbers come from `numbers.precisionPct/recallPct/clusters` in theme.ts —
// measured on the 32-scenario calibration run; replace those if a longer
// smoke gives tighter CIs.

const SMOKE = {
  // Aggregate precision / recall on the human-labeled calibration subset.
  precisionPct: numbers.precisionPct,
  recallPct: numbers.recallPct,
  precisionCi: [numbers.precisionCiLow, numbers.precisionCiHigh] as const,
  // Confusion matrix counts (rows = human label, cols = judge label).
  // [missed_approach, failed_grip, abstain]. Shape sized for n = 16 labeled.
  confusion: {
    missed_approach: { missed_approach: 7, failed_grip: 0, abstain: 0 },
    failed_grip: { missed_approach: 1, failed_grip: 7, abstain: 1 },
  },
  // Top deployment cluster cards. `count` totals to ~`numbers.scenariosDep`.
  clusters: [
    { id: "C1", label: "missed_approach", count: 612, summary: "Open-fingers approach skims past cube" },
    { id: "C2", label: "failed_grip", count: 388, summary: "Fingers graze cube during close — slip" },
    { id: "C3", label: "missed_approach", count: 142, summary: "Lateral overshoot at +x edge" },
    { id: "C4", label: "abstain", count: 88, summary: "No-contact rollouts · point = null" },
  ],
};

const fmtPct = (n: number) => `${Math.round(n)}%`;

export const JudgeTrustScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Beat timings in frames.
  const T_MATRIX = 0;
  const T_NUMBERS = fps * 1.5;
  const T_FLY = fps * 5;
  const T_LAND = fps * 7.5;
  const T_BANNER = fps * 12.5;

  const headerOp = useFadeIn(frame, 0, 16);
  const matrixOp = useFadeIn(frame, T_MATRIX + 4, 18);
  const numbersOp = useFadeIn(frame, T_NUMBERS, 18);

  // Cluster cards land staggered after the chips fly.
  const clusterStarts = SMOKE.clusters.map((_, i) => T_LAND + i * 6);

  // Banner.
  const bannerOp = useFadeIn(frame, T_BANNER, 20);
  const bannerScale = spring({
    frame: frame - T_BANNER,
    fps,
    config: { damping: 18, stiffness: 160, mass: 0.7 },
  });

  return (
    <AbsoluteFill
      style={{
        paddingTop: 124,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "column",
        gap: 18,
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
          Judge calibration · human labels ⋈ findings
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
          We don&rsquo;t just grade the robot.{" "}
          <span style={{ color: colors.accent }}>We grade the grader.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 28, flex: 1, marginTop: 16 }}>
        {/* LEFT: confusion matrix */}
        <div
          style={{
            flex: 0.85,
            opacity: matrixOp,
            background: colors.surface,
            border: `1px solid ${colors.line}`,
            borderRadius: 16,
            padding: 22,
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              letterSpacing: 2,
              color: colors.ink4,
              textTransform: "uppercase",
            }}
          >
            Calibration confusion matrix · n = 16 labeled rollouts
          </div>

          <ConfusionMatrix
            data={SMOKE.confusion}
            precisionPct={SMOKE.precisionPct}
            recallPct={SMOKE.recallPct}
            ciLow={SMOKE.precisionCi[0]}
            ciHigh={SMOKE.precisionCi[1]}
            numbersOpacity={numbersOp}
            chipsLiftAt={T_FLY}
            chipsHideAt={T_FLY + 12}
            frame={frame}
          />

          <div
            style={{
              marginTop: "auto",
              fontFamily: fonts.mono,
              fontSize: 12,
              color: colors.ink3,
              lineHeight: 1.5,
            }}
          >
            Rows: human label · Cols: judge label · Off-diagonal = disagreement.
            Per-label{" "}
            <span style={{ color: colors.ink, fontWeight: 600 }}>precision</span>{" "}
            becomes the trust chip on every deployment finding.
          </div>
        </div>

        {/* RIGHT: deployment cluster cards with chips landing */}
        <div
          style={{
            flex: 1.15,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 11,
              letterSpacing: 2,
              color: colors.dep,
              textTransform: "uppercase",
              opacity: useFadeIn(frame, T_LAND - 12, 16),
            }}
          >
            ● Deployment findings · BC-RNN under perturbation
          </div>

          {SMOKE.clusters.map((c, i) => (
            <ClusterCard
              key={c.id}
              cluster={c}
              trustPct={SMOKE.precisionPct}
              enterAt={clusterStarts[i]}
              chipLandAt={clusterStarts[i] + 6}
              frame={frame}
            />
          ))}
        </div>
      </div>

      {/* Bottom banner reveal — the lean-forward moment. */}
      <div
        style={{
          opacity: bannerOp,
          transform: `scale(${0.96 + bannerScale * 0.04})`,
          transformOrigin: "center",
          background: `linear-gradient(90deg, ${colors.cal}10, ${colors.dep}10)`,
          border: `2px solid ${colors.accent}`,
          borderRadius: 14,
          padding: "18px 28px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 18,
          boxShadow: `0 0 0 6px ${colors.accent}14`,
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 12,
            letterSpacing: 2,
            color: colors.accent,
            textTransform: "uppercase",
            fontWeight: 600,
          }}
        >
          Judge Trust
        </div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 600,
            color: colors.ink,
            letterSpacing: -0.4,
          }}
        >
          Same task. Same camera.{" "}
          <span style={{ color: colors.accent }}>
            Calibration precision transfers directly to deployment findings.
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ----------------------- Confusion matrix --------------------------------

const ROWS = ["missed_approach", "failed_grip"] as const;
const COLS = ["missed_approach", "failed_grip", "abstain"] as const;

type ConfusionRow = { missed_approach: number; failed_grip: number; abstain: number };

const ConfusionMatrix: React.FC<{
  data: { missed_approach: ConfusionRow; failed_grip: ConfusionRow };
  precisionPct: number;
  recallPct: number;
  ciLow: number;
  ciHigh: number;
  numbersOpacity: number;
  chipsLiftAt: number;
  chipsHideAt: number;
  frame: number;
}> = ({ data, precisionPct, recallPct, ciLow, ciHigh, numbersOpacity, chipsLiftAt, chipsHideAt, frame }) => {
  // Chip lift: opacity tracks the time the chip is sitting on the matrix.
  const chipOnMatrix = interpolate(
    frame,
    [chipsLiftAt - 6, chipsLiftAt, chipsHideAt - 4, chipsHideAt],
    [1, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <div style={{ marginTop: 6 }}>
      {/* Column headers */}
      <div style={{ display: "grid", gridTemplateColumns: "180px repeat(3, 1fr)", gap: 6 }}>
        <div />
        {COLS.map((c) => (
          <div
            key={c}
            style={{
              fontFamily: fonts.mono,
              fontSize: 10,
              letterSpacing: 1,
              color: colors.ink4,
              textTransform: "uppercase",
              textAlign: "center",
              paddingBottom: 6,
            }}
          >
            {c}
          </div>
        ))}

        {/* Rows */}
        {ROWS.map((r) => (
          <React.Fragment key={r}>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
                alignItems: "flex-end",
                paddingRight: 10,
                fontFamily: fonts.mono,
                fontSize: 11,
                color: colors.ink3,
                textTransform: "uppercase",
                letterSpacing: 1,
              }}
            >
              {r}
            </div>
            {COLS.map((c) => {
              const v = data[r][c];
              const isDiag = r === c;
              return (
                <div
                  key={c}
                  style={{
                    height: 64,
                    borderRadius: 8,
                    background: isDiag
                      ? `${colors.ok}1A`
                      : v > 0
                        ? `${colors.err}10`
                        : colors.surface2,
                    border: `1px solid ${isDiag ? colors.ok : colors.line2}`,
                    display: "grid",
                    placeItems: "center",
                    fontVariantNumeric: "tabular-nums",
                    fontSize: 26,
                    fontWeight: 600,
                    color: isDiag ? colors.ok : v > 0 ? colors.err : colors.ink4,
                    opacity: numbersOpacity,
                  }}
                >
                  {v}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>

      {/* Aggregate precision / recall chips sitting under the matrix */}
      <div
        style={{
          marginTop: 14,
          display: "flex",
          gap: 12,
          opacity: chipOnMatrix,
        }}
      >
        <Chip label="precision" value={fmtPct(precisionPct)} ciLow={ciLow} ciHigh={ciHigh} />
        <Chip label="recall" value={fmtPct(recallPct)} />
      </div>
    </div>
  );
};

const Chip: React.FC<{ label: string; value: string; ciLow?: number; ciHigh?: number }> = ({
  label,
  value,
  ciLow,
  ciHigh,
}) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "6px 12px",
      borderRadius: 999,
      background: colors.surface,
      border: `1px solid ${colors.ok}`,
      fontFamily: fonts.mono,
      fontSize: 12,
      color: colors.ink2,
      boxShadow: `0 0 0 3px ${colors.ok}14`,
    }}
  >
    <span style={{ color: colors.ink4 }}>{label}</span>
    <span style={{ color: colors.ok, fontWeight: 600 }}>{value}</span>
    {ciLow !== undefined && ciHigh !== undefined ? (
      <span style={{ color: colors.ink4 }}>
        95% CI [{ciLow}–{ciHigh}]
      </span>
    ) : null}
  </div>
);

// ----------------------- Cluster card ------------------------------------

const ClusterCard: React.FC<{
  cluster: { id: string; label: string; count: number; summary: string };
  trustPct: number;
  enterAt: number;
  chipLandAt: number;
  frame: number;
}> = ({ cluster, trustPct, enterAt, chipLandAt, frame }) => {
  const op = useFadeIn(frame, enterAt, 16);
  const slideY = interpolate(
    frame,
    [enterAt, enterAt + 22],
    [22, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  // Trust chip flies in from the LEFT (off-card) and lands on the right side.
  const chipX = interpolate(
    frame,
    [chipLandAt - 8, chipLandAt],
    [-220, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  const chipOp = useFadeIn(frame, chipLandAt - 6, 14);

  return (
    <div
      style={{
        opacity: op,
        transform: `translateY(${slideY}px)`,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 12,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 18,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink4,
          width: 32,
        }}
      >
        {cluster.id}
      </div>
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontSize: 18,
            color: colors.ink,
            fontWeight: 600,
            letterSpacing: -0.3,
          }}
        >
          {cluster.summary}
        </div>
        <div
          style={{
            marginTop: 4,
            fontFamily: fonts.mono,
            fontSize: 12,
            color: colors.ink3,
          }}
        >
          {cluster.label} · {cluster.count} rollouts
        </div>
      </div>

      {/* Trust chip — flies in from the matrix */}
      <div
        style={{
          opacity: chipOp,
          transform: `translateX(${chipX}px)`,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 12px",
          borderRadius: 999,
          background: colors.okSoft,
          border: `1px solid ${colors.ok}`,
          fontFamily: fonts.mono,
          fontSize: 12,
        }}
      >
        <span style={{ color: colors.ink4 }}>judge trust</span>
        <span style={{ color: colors.ok, fontWeight: 700 }}>
          {fmtPct(trustPct)}
        </span>
      </div>
    </div>
  );
};

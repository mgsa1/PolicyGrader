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

// 20–28 s · Two populations.
// Split-screen amber (benchmark) / steel-blue (deployment).
// Cal: 3 frames in a row · Dep: 2×3 grid + stacked-card depth shadow.
// The visual asymmetry IS the story — n=50 vs n=2870.
const CAL_FRAMES = ["cal_03.png", "cal_04.png", "cal_07.png"];
const DEP_FRAMES = [
  "dep_02.png",
  "dep_05.png",
  "dep_07.png",
  "dep_09.png",
  "dep_11.png",
  "dep_13.png",
];

const Side: React.FC<{
  align: "left" | "right";
  cohort: "cal" | "dep";
  cohortLabel: string;
  title: string;
  callout: string;
  policy: string;
  truth: string;
  frames: string[];
  enterAt: number;
  sampleSize: number;
}> = ({
  align,
  cohort,
  cohortLabel,
  title,
  callout,
  policy,
  truth,
  frames,
  enterAt,
  sampleSize,
}) => {
  const frame = useCurrentFrame();
  const accent = cohort === "cal" ? colors.cal : colors.dep;
  const accentSoft = cohort === "cal" ? colors.calSoft : colors.depSoft;
  const accentLine = cohort === "cal" ? colors.calLine : colors.depLine;
  const isDep = cohort === "dep";

  const op = useFadeIn(frame, enterAt, 22);
  const slideX = interpolate(
    frame,
    [enterAt, enterAt + 26],
    [align === "left" ? -40 : 40, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  return (
    <div
      style={{
        flex: 1,
        position: "relative",
        opacity: op,
        transform: `translateX(${slideX}px)`,
        display: "flex",
      }}
    >
      {/* Stacked-card depth shadow on deployment side — implies thousands behind */}
      {isDep && (
        <>
          <div
            style={{
              position: "absolute",
              inset: 0,
              transform: "translate(18px, 18px)",
              background: accentSoft,
              border: `1px solid ${accentLine}`,
              borderRadius: 20,
              opacity: 0.45,
            }}
          />
          <div
            style={{
              position: "absolute",
              inset: 0,
              transform: "translate(9px, 9px)",
              background: accentSoft,
              border: `1px solid ${accentLine}`,
              borderRadius: 20,
              opacity: 0.7,
            }}
          />
        </>
      )}

      <div
        style={{
          flex: 1,
          position: "relative",
          display: "flex",
          flexDirection: "column",
          gap: 22,
          padding: 40,
          background: accentSoft,
          borderRadius: 20,
          border: `1px solid ${accentLine}`,
          overflow: "hidden",
        }}
      >
        {/* Cohort tag + sample-size chip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 12,
              letterSpacing: 2.4,
              color: accent,
              textTransform: "uppercase",
              fontWeight: 600,
            }}
          >
            ● {cohortLabel}
          </div>
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: isDep ? 12 : 11,
              letterSpacing: 1.2,
              padding: "3px 10px",
              borderRadius: 999,
              border: `1px solid ${accentLine}`,
              color: accent,
              background: "rgba(255,255,255,0.55)",
              fontWeight: isDep ? 700 : 500,
            }}
          >
            n = {sampleSize.toLocaleString()}
          </div>
        </div>

        <div
          style={{
            fontSize: 38,
            fontWeight: 600,
            color: colors.ink,
            letterSpacing: -0.5,
            lineHeight: 1.05,
          }}
        >
          {title}
        </div>

        {/* Frame grid: 1 row of 3 (cal) or 2 rows of 3 (dep). Same column template. */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 10,
            marginTop: 4,
          }}
        >
          {frames.map((f, i) => {
            const fop = useFadeIn(frame, enterAt + 19 + i * 6, 19);
            return (
              <div
                key={f}
                style={{
                  aspectRatio: "1 / 1",
                  borderRadius: 10,
                  overflow: "hidden",
                  background: colors.surface,
                  opacity: fop,
                  boxShadow: `0 0 0 1px ${accentLine}`,
                }}
              >
                <Img
                  src={staticFile(`keyframes/${f}`)}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              </div>
            );
          })}
        </div>

        {/* Action callout — what we do with this side */}
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 14,
            letterSpacing: 1,
            color: accent,
            fontWeight: 600,
          }}
        >
          {callout}
        </div>

        {/* Two-row meta */}
        <div
          style={{
            marginTop: "auto",
            fontFamily: fonts.mono,
            fontSize: 13,
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            rowGap: 8,
            columnGap: 16,
            color: colors.ink2,
            paddingTop: 16,
            borderTop: `1px dashed ${accentLine}`,
          }}
        >
          <span style={{ color: colors.ink4, letterSpacing: 1.2 }}>POLICY</span>
          <span>{policy}</span>
          <span style={{ color: colors.ink4, letterSpacing: 1.2 }}>TRUTH</span>
          <span>{truth}</span>
        </div>
      </div>
    </div>
  );
};

export const PopulationsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOp = useFadeIn(frame, 0, 22);
  const taglineOp = useFadeIn(frame, 115, 26);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 130,
        paddingLeft: 140,
        paddingRight: 140,
        display: "flex",
        flexDirection: "column",
        gap: 28,
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
          Minimum human oversight · Complete policy stress test
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
          Benchmark the judge on a few human-labeled failures.
          <br />
          <span style={{ color: colors.ink3 }}>Apply it to the real policy.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 32, flex: 1 }}>
        <Side
          align="left"
          cohort="cal"
          cohortLabel="Benchmark"
          title="Validate the performance with a small human labelled subset"
          callout="→ measure judge P/R"
          policy="Lift IK · injected"
          truth="HUMAN labels · stratified subset"
          frames={CAL_FRAMES}
          enterAt={12}
          sampleSize={50}
        />
        <Side
          align="right"
          cohort="dep"
          cohortLabel="Deployment"
          title="Auto-evaluate the policy under stress test"
          callout="→ apply judge with measured precision"
          policy="BC-RNN · cube_xy_jitter_m=0.15"
          truth="JUDGE labels · with benchmark precision"
          frames={DEP_FRAMES}
          enterAt={34}
          sampleSize={2870}
        />
      </div>

      <div
        style={{
          opacity: taglineOp,
          textAlign: "center",
          fontSize: 22,
          fontWeight: 500,
          color: colors.ink2,
        }}
      >
        Same task · same camera ·{" "}
        <span style={{ color: colors.accent, fontWeight: 600 }}>
          benchmark precision transfers directly.
        </span>
      </div>
    </AbsoluteFill>
  );
};

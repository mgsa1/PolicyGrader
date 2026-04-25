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

// 20–28 s · Two populations.
// Split-screen amber (calibration) / steel-blue (deployment).
// Three keyframes per side. Tagline at the bottom.
const CAL_FRAMES = ["cal_03.png", "cal_04.png", "cal_07.png"];
const DEP_FRAMES = ["dep_02.png", "dep_06.png", "dep_11.png"];

const Side: React.FC<{
  align: "left" | "right";
  cohort: "cal" | "dep";
  title: string;
  subtitle: string;
  policy: string;
  truth: string;
  frames: string[];
  enterAt: number;
  sampleSize: number;
}> = ({ align, cohort, title, subtitle, policy, truth, frames, enterAt, sampleSize }) => {
  const frame = useCurrentFrame();
  const accent = cohort === "cal" ? colors.cal : colors.dep;
  const accentSoft = cohort === "cal" ? colors.calSoft : colors.depSoft;
  const accentLine = cohort === "cal" ? colors.calLine : colors.depLine;

  const op = useFadeIn(frame, enterAt, 18);
  const slideX = interpolate(
    frame,
    [enterAt, enterAt + 22],
    [align === "left" ? -40 : 40, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  return (
    <div
      style={{
        flex: 1,
        opacity: op,
        transform: `translateX(${slideX}px)`,
        display: "flex",
        flexDirection: "column",
        gap: 22,
        padding: 40,
        background: accentSoft,
        borderRadius: 20,
        border: `1px solid ${accentLine}`,
        position: "relative",
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
          ● {cohort === "cal" ? "Calibration" : "Deployment"}
        </div>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 11,
            letterSpacing: 1.2,
            padding: "3px 10px",
            borderRadius: 999,
            border: `1px solid ${accentLine}`,
            color: accent,
            background: "rgba(255,255,255,0.55)",
          }}
        >
          n = {sampleSize}
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
      <div
        style={{
          fontSize: 16,
          color: colors.ink3,
          lineHeight: 1.45,
          maxWidth: 540,
        }}
      >
        {subtitle}
      </div>

      {/* Frame triplet */}
      <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
        {frames.map((f, i) => {
          const fop = useFadeIn(frame, enterAt + 16 + i * 6, 16);
          return (
            <div
              key={f}
              style={{
                flex: 1,
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
  );
};

export const PopulationsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOp = useFadeIn(frame, 0, 18);
  const taglineOp = useFadeIn(frame, 96, 22);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 130,
        paddingLeft: 64,
        paddingRight: 64,
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
          Two populations · same task · same camera
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
          Calibrate the judge with humans.
          <br />
          <span style={{ color: colors.ink3 }}>Apply it to the real policy.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 24, flex: 1 }}>
        <Side
          align="left"
          cohort="cal"
          title="Scripted policy with injected failures"
          subtitle="Knobs steer the IK picker into specific failure regimes — action_noise, angle_deg, premature_close, grip_scale. We don't trust the knob; we trust the human."
          policy="Lift IK · injected"
          truth="HUMAN labels · stratified subset"
          frames={CAL_FRAMES}
          enterAt={10}
          sampleSize={1600}
        />
        <Side
          align="right"
          cohort="dep"
          title="Pretrained BC-RNN under perturbation"
          subtitle="robomimic Lift checkpoint, cube placement widened from ±3 cm to ±15 cm — a clean OOD stress test of a real policy."
          policy="BC-RNN · cube_xy_jitter_m=0.15"
          truth="Inherits calibration P/R chips"
          frames={DEP_FRAMES}
          enterAt={28}
          sampleSize={1230}
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
          calibration precision transfers directly.
        </span>
      </div>
    </AbsoluteFill>
  );
};

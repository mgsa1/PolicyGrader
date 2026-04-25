import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { colors, fonts, numbers } from "../theme";

// Persistent product topbar.
// Right side mirrors the dashboard's live banner: $ spent · elapsed · scenarios.
// Numbers ramp from 0 to the final values across the whole composition, so the
// topbar reads like a session that's running while the video plays.

const usd = (n: number) =>
  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });

export const Topbar: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const fadeOp = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Linear ramp 0 → final across the whole composition. Topbar reads as
  // a session that's running while the video plays.
  const t = Math.min(1, frame / durationInFrames);
  const cost = numbers.pipelineCostUsd * t;
  const scenarios = numbers.scenarios * t;
  const calCount = Math.round(scenarios * 0.5);
  const depCount = Math.round(scenarios) - calCount;

  return (
    <div
      style={{
        position: "absolute",
        top: 32,
        left: 48,
        right: 48,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        opacity: fadeOp,
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: colors.ink,
            color: "#fff",
            fontFamily: fonts.sans,
            fontWeight: 700,
            fontSize: 13,
            display: "grid",
            placeItems: "center",
            letterSpacing: 0.5,
          }}
        >
          PG
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            lineHeight: 1.15,
          }}
        >
          <span style={{ fontSize: 16, fontWeight: 600, color: colors.ink }}>
            PolicyGrader
          </span>
          <span style={{ fontSize: 12, color: colors.ink4, fontFamily: fonts.mono }}>
            Powered by Claude Opus 4.7
          </span>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 18,
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink2,
          background: colors.surface,
          border: `1px solid ${colors.line}`,
          padding: "8px 16px",
          borderRadius: 999,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: colors.ok,
              boxShadow: `0 0 10px ${colors.ok}`,
            }}
          />
          <span style={{ color: colors.ok, fontWeight: 600, letterSpacing: 1.4 }}>
            LIVE
          </span>
        </span>
        <span style={{ color: colors.line2 }}>·</span>
        <span>{usd(cost)}</span>
        <span style={{ color: colors.line2 }}>·</span>
        <span>
          {Math.round(scenarios).toLocaleString()}
          {" "}
          <span style={{ color: colors.ink4 }}>scenarios</span>
        </span>
        <span style={{ color: colors.line2 }}>·</span>
        <span>
          <span style={{ color: colors.cal, fontWeight: 600 }}>{calCount}</span>
          <span style={{ color: colors.ink4 }}> cal · </span>
          <span style={{ color: colors.dep, fontWeight: 600 }}>{depCount}</span>
          <span style={{ color: colors.ink4 }}> dep</span>
        </span>
      </div>
    </div>
  );
};

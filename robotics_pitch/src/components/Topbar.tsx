import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { colors, fonts } from "../theme";

// Persistent product topbar: PG monogram + "Embodied Eval Orchestrator".
// Fades in over the first 0.5 s and stays.
export const Topbar: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

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
        opacity,
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
            Embodied Eval Orchestrator
          </span>
          <span style={{ fontSize: 12, color: colors.ink4, fontFamily: fonts.mono }}>
            policy-grader · powered by Claude Opus 4.7
          </span>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink3,
          background: colors.surface,
          border: `1px solid ${colors.line}`,
          padding: "8px 14px",
          borderRadius: 999,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 999,
            background: colors.ok,
            display: "inline-block",
            boxShadow: `0 0 10px ${colors.ok}`,
          }}
        />
        Anthropic · Opus 4.7 Hackathon
      </div>
    </div>
  );
};

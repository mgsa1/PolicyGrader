import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { colors, fonts } from "../theme";

interface PhaseCardProps {
  index: number;
  total: number;
  number: string; // "01"
  name: string; // "PLANNER"
  artifact: string; // "plan.md"
  detail: string; // "designs the test suite"
  color: string;
  delayFrames: number;
  highlight?: boolean;
  badge?: string; // small "×K parallel" badge
}

export const PhaseCard: React.FC<PhaseCardProps> = ({
  index,
  total,
  number,
  name,
  artifact,
  detail,
  color,
  delayFrames,
  highlight = false,
  badge,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const enterAt = delayFrames;
  const fadeOp = interpolate(frame, [enterAt, enterAt + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  const slideY = interpolate(frame, [enterAt, enterAt + 22], [28, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // Artifact appears a beat after the card.
  const artifactOp = interpolate(
    frame,
    [enterAt + 14, enterAt + 28],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <div
      style={{
        flex: 1,
        position: "relative",
        background: colors.surface,
        border: `1px solid ${highlight ? color : colors.line}`,
        borderRadius: 14,
        padding: "20px 22px",
        opacity: fadeOp,
        transform: `translateY(${slideY}px)`,
        boxShadow: highlight
          ? `0 0 0 4px ${color}20, 0 12px 30px rgba(31,31,31,0.06)`
          : "0 4px 14px rgba(31,31,31,0.04)",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 160,
      }}
    >
      {/* Phase color strip */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 4,
          borderTopLeftRadius: 14,
          borderTopRightRadius: 14,
          background: color,
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 4,
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 11,
            letterSpacing: 1.6,
            color: colors.ink4,
          }}
        >
          {number} / {String(total).padStart(2, "0")}
        </div>
        {badge ? (
          <div
            style={{
              fontFamily: fonts.mono,
              fontSize: 10,
              letterSpacing: 1.2,
              padding: "3px 8px",
              borderRadius: 999,
              background: `${color}18`,
              color: color,
              border: `1px solid ${color}40`,
              textTransform: "uppercase",
            }}
          >
            {badge}
          </div>
        ) : null}
      </div>

      <div
        style={{
          fontSize: 22,
          fontWeight: 600,
          color: colors.ink,
          letterSpacing: -0.3,
        }}
      >
        {name}
      </div>
      <div
        style={{
          fontSize: 13,
          color: colors.ink3,
          lineHeight: 1.4,
        }}
      >
        {detail}
      </div>

      <div
        style={{
          marginTop: "auto",
          paddingTop: 10,
          borderTop: `1px dashed ${colors.line2}`,
          fontFamily: fonts.mono,
          fontSize: 12,
          color: color,
          opacity: artifactOp,
          letterSpacing: 0.2,
        }}
      >
        ↳ {artifact}
      </div>
    </div>
  );
};

import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 0:33–0:48 · Name reveal.
//
// Centered title block — PolicyGrader · tagline · "Powered by Claude Opus
// 4.7 and Claude Managed Agents". Nothing else on screen. Vertically +
// horizontally centered for the full duration.

export const NameRevealScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const eyebrowOp = useFadeIn(frame, 6, 18);
  const titleOp = useFadeIn(frame, 14, 22);
  const titleScale = spring({
    frame: frame - 14,
    fps,
    config: { damping: 18, stiffness: 160, mass: 0.7 },
  });
  const taglineOp = useFadeIn(frame, 36, 22);
  const poweredOp = useFadeIn(frame, 56, 22);

  return (
    <AbsoluteFill style={{ position: "relative" }}>
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "0 96px",
        }}
      >
        <div
          style={{
            opacity: eyebrowOp,
            fontFamily: fonts.mono,
            fontSize: 13,
            letterSpacing: 2.8,
            color: colors.ink4,
            textTransform: "uppercase",
            display: "inline-flex",
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
            marginTop: 22,
            opacity: titleOp,
            transform: `scale(${0.96 + titleScale * 0.04})`,
            fontSize: 168,
            fontWeight: 700,
            lineHeight: 0.95,
            letterSpacing: -4.4,
            color: colors.ink,
          }}
        >
          Policy<span style={{ color: colors.accent }}>Grader</span>
          <span style={{ color: colors.ink3, fontWeight: 500 }}>.</span>
        </div>

        <div
          style={{
            opacity: taglineOp,
            marginTop: 28,
            fontSize: 36,
            color: colors.ink2,
            lineHeight: 1.3,
            letterSpacing: -0.4,
          }}
        >
          <span style={{ fontWeight: 600, color: colors.ink }}>
            One prompt in.
          </span>{" "}
          <span style={{ color: colors.ink3 }}>A full control policy stress test out.</span>
        </div>

        <div
          style={{
            opacity: poweredOp,
            marginTop: 18,
            fontFamily: fonts.mono,
            fontSize: 16,
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
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

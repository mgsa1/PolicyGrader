import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, Img, staticFile } from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn, useSlideUp } from "../components/easing";

// 0–4 s · "Embodied AI is everywhere. Evaluating it isn't."
// One vignette of a Lift-task keyframe drifts on the right, type-on title
// on the left.
export const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const eyebrowOp = useFadeIn(frame, 6, 12);
  const lineAOp = useFadeIn(frame, 14, 16);
  const lineAY = useSlideUp(frame, 14, 30, 0, 22);
  const lineBOp = useFadeIn(frame, 30, 18);
  const lineBY = useSlideUp(frame, 30, 30, 0, 24);

  // Vignette drifts right-to-left, slowly.
  const vignetteX = useSlideUp(frame, 0, -30, 0, fps * 4);
  const vignetteOp = useFadeIn(frame, 4, 24);

  return (
    <AbsoluteFill style={{ display: "flex", flexDirection: "row" }}>
      {/* LEFT: title */}
      <div
        style={{
          flex: 1.2,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          paddingLeft: 96,
          paddingRight: 64,
        }}
      >
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 13,
            letterSpacing: 3,
            color: colors.ink4,
            textTransform: "uppercase",
            opacity: eyebrowOp,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: colors.cal,
              boxShadow: `0 0 12px ${colors.cal}`,
            }}
          />
          Anthropic · Opus 4.7 Hackathon
        </div>

        <div
          style={{
            fontSize: 88,
            fontWeight: 600,
            lineHeight: 1.02,
            letterSpacing: -1.5,
            marginTop: 32,
            color: colors.ink,
            opacity: lineAOp,
            transform: `translateY(${lineAY}px)`,
          }}
        >
          Embodied AI is everywhere.
        </div>

        <div
          style={{
            fontSize: 88,
            fontWeight: 600,
            lineHeight: 1.02,
            letterSpacing: -1.5,
            marginTop: 8,
            color: colors.ink3,
            opacity: lineBOp,
            transform: `translateY(${lineBY}px)`,
          }}
        >
          Evaluating it{" "}
          <span style={{ color: colors.accent, fontWeight: 700 }}>isn&rsquo;t</span>.
        </div>
      </div>

      {/* RIGHT: keyframe vignette */}
      <div
        style={{
          flex: 1,
          position: "relative",
          display: "grid",
          placeItems: "center",
          opacity: vignetteOp,
          transform: `translateX(${vignetteX}px)`,
        }}
      >
        <div
          style={{
            position: "relative",
            width: 560,
            height: 560,
            borderRadius: 28,
            overflow: "hidden",
            boxShadow:
              "0 24px 60px rgba(31,31,31,0.10), 0 0 0 1px rgba(31,31,31,0.06)",
            background: colors.surface,
          }}
        >
          <Img
            src={staticFile("keyframes/cal_03.png")}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "saturate(1.05)",
            }}
          />
          {/* Soft grain via gradient */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(180deg, rgba(31,31,31,0) 0%, rgba(31,31,31,0) 60%, rgba(31,31,31,0.18) 100%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 24,
              bottom: 20,
              fontFamily: fonts.mono,
              fontSize: 11,
              letterSpacing: 1.4,
              color: "rgba(255,255,255,0.85)",
              textTransform: "uppercase",
            }}
          >
            robosuite · Lift · frontview
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

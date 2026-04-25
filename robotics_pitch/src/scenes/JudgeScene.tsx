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

// 28–34 s · The judge.
// Two halves separated horizontally:
//   LEFT: dep_14 with growing pulse ring at the contact point — "POINTS"
//   RIGHT: dep_04 — "ABSTAINS · point: null"

// Approximate normalized coordinates of the red dot on dep_14.png
// (estimated from the rendered keyframe — gripper-cube contact area).
const DOT_X = 0.535;
const DOT_Y = 0.46;

const Card: React.FC<{
  enterAt: number;
  src: string;
  label: string;
  hasPoint: boolean;
  caption: string;
  description: string;
}> = ({ enterAt, src, label, hasPoint, caption, description }) => {
  const frame = useCurrentFrame();
  const op = useFadeIn(frame, enterAt, 14);
  const slideY = interpolate(
    frame,
    [enterAt, enterAt + 22],
    [22, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  // Pulse ring grows + fades, repeating.
  const pulsePhase = ((frame - (enterAt + 12)) % 32) / 32;
  const pulseScale = interpolate(pulsePhase, [0, 1], [0.6, 2.2]);
  const pulseOp = interpolate(pulsePhase, [0, 0.6, 1], [0.6, 0.2, 0]);

  // Frame strip at the top — flickers through ~12 indices then settles.
  const settleAt = enterAt + 22;
  const flickerIndex =
    frame < settleAt ? (frame - enterAt) % 12 : 11; // arbitrary "settled" position

  return (
    <div
      style={{
        flex: 1,
        opacity: op,
        transform: `translateY(${slideY}px)`,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 18,
        padding: 28,
        display: "flex",
        flexDirection: "column",
        gap: 18,
      }}
    >
      {/* Frame-strip indicator */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 4,
        }}
      >
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 6,
              borderRadius: 2,
              background: i === flickerIndex ? colors.accent : colors.line2,
              transition: "background 0.05s",
            }}
          />
        ))}
      </div>

      <div
        style={{
          position: "relative",
          width: "100%",
          height: 480,
          borderRadius: 12,
          overflow: "hidden",
          background: colors.surface2,
        }}
      >
        <Img
          src={staticFile(`keyframes/${src}`)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />

        {hasPoint ? (
          <>
            {/* Pulsing ring */}
            <div
              style={{
                position: "absolute",
                left: `${DOT_X * 100}%`,
                top: `${DOT_Y * 100}%`,
                width: 56,
                height: 56,
                marginLeft: -28,
                marginTop: -28,
                borderRadius: 999,
                border: `3px solid ${colors.err}`,
                transform: `scale(${pulseScale})`,
                opacity: pulseOp,
                pointerEvents: "none",
              }}
            />
            {/* Static center dot — actually the keyframe already has one
                baked in, this is reinforcement. */}
            <div
              style={{
                position: "absolute",
                left: `${DOT_X * 100}%`,
                top: `${DOT_Y * 100}%`,
                width: 14,
                height: 14,
                marginLeft: -7,
                marginTop: -7,
                borderRadius: 999,
                background: colors.err,
                boxShadow: `0 0 16px ${colors.err}`,
                pointerEvents: "none",
              }}
            />
          </>
        ) : (
          // "abstention badge" floating in the upper-right
          <div
            style={{
              position: "absolute",
              top: 14,
              right: 14,
              fontFamily: fonts.mono,
              fontSize: 12,
              padding: "6px 12px",
              borderRadius: 999,
              background: "rgba(255,255,255,0.92)",
              border: `1px solid ${colors.line2}`,
              color: colors.ink2,
              letterSpacing: 0.4,
            }}
          >
            point&nbsp;<span style={{ color: colors.err }}>= null</span>
          </div>
        )}
      </div>

      {/* Caption strip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink3,
        }}
      >
        <span>{caption}</span>
        <span
          style={{
            padding: "4px 10px",
            borderRadius: 6,
            background: hasPoint ? colors.errSoft : colors.surface2,
            color: hasPoint ? colors.err : colors.ink2,
            border: `1px solid ${hasPoint ? colors.err : colors.line2}`,
          }}
        >
          {label}
        </span>
      </div>

      <div
        style={{
          fontSize: 17,
          color: colors.ink2,
          lineHeight: 1.45,
        }}
      >
        {description}
      </div>
    </div>
  );
};

export const JudgeScene: React.FC = () => {
  const frame = useCurrentFrame();
  const headerOp = useFadeIn(frame, 0, 16);
  const taglineOp = useFadeIn(frame, 80, 18);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 124,
        paddingLeft: 64,
        paddingRight: 64,
        display: "flex",
        flexDirection: "column",
        gap: 22,
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
          The judge · 2 576 px vision · 12–36 frames per rollout
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
          Names <span style={{ color: colors.ink3 }}>what</span> failed.{" "}
          <span style={{ color: colors.err }}>Points where it broke.</span>
          <br />
          <span style={{ color: colors.ink3 }}>Or honestly </span>
          <span style={{ color: colors.accent, fontWeight: 700 }}>abstains</span>
          <span style={{ color: colors.ink3 }}>.</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 24, flex: 1 }}>
        <Card
          enterAt={6}
          src="dep_14.png"
          label="failed_grip · point=(403, 312)"
          hasPoint
          caption="dep_14.png · POINTS"
          description="The fingers grazed the cube as they closed. The judge points at the exact contact pixel."
        />
        <Card
          enterAt={26}
          src="dep_04.png"
          label="missed_approach · point = null"
          hasPoint={false}
          caption="dep_04.png · ABSTAINS"
          description="The gripper closed on empty air — there is no contact pixel to point at. The judge returns null instead of guessing."
        />
      </div>

      <div
        style={{
          opacity: taglineOp,
          textAlign: "center",
          fontSize: 18,
          color: colors.ink3,
          fontFamily: fonts.mono,
          letterSpacing: 0.4,
        }}
      >
        Pixel-accurate when there&rsquo;s evidence.{" "}
        <span style={{ color: colors.ok }}>
          Honestly silent when there isn&rsquo;t.
        </span>
      </div>
    </AbsoluteFill>
  );
};

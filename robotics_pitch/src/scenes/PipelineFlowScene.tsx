import React from "react";
import {
  AbsoluteFill,
  Easing,
  Loop,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";
import {
  Arrow,
  JudgesBox,
  PROMPT_TEXT,
  PromptBox,
  ROLLOUT_LOOP_FRAMES,
  ROLLOUT_VIDEOS,
  ReportBox,
} from "./PipelineScene";

// Standalone flow row, reusing the components from PipelineScene with their
// timing reset so the four boxes animate in from frame 0. Sized for a tight
// README banner (no subtitle — the cards GIF above already names the flow).

export const PipelineFlowScene: React.FC = () => {
  const frame = useCurrentFrame();

  const T_PROMPT_ENTER = 8;
  const T_PROMPT_TYPED = T_PROMPT_ENTER + 24;
  const T_ROLLOUTS_OUT = T_PROMPT_TYPED + 24;
  const T_JUDGES_OUT = T_ROLLOUTS_OUT + 50;
  const T_REPORT_OUT = T_JUDGES_OUT + 45;

  return (
    <AbsoluteFill
      style={{
        paddingTop: 32,
        paddingLeft: 64,
        paddingRight: 64,
        paddingBottom: 32,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1.1fr 28px 1.4fr 28px 1.1fr 28px 0.9fr",
          alignItems: "stretch",
          gap: 0,
        }}
      >
        <PromptBox
          text={PROMPT_TEXT}
          enterAt={T_PROMPT_ENTER}
          finishAt={T_PROMPT_TYPED}
          frame={frame}
        />
        <Arrow color={colors.phasePlanner} activeAt={T_PROMPT_TYPED} frame={frame} />
        <FlowRolloutsBox enterAt={T_ROLLOUTS_OUT} frame={frame} />
        <Arrow color={colors.phaseJudge} activeAt={T_JUDGES_OUT} frame={frame} />
        <JudgesBox enterAt={T_JUDGES_OUT} frame={frame} />
        <Arrow color={colors.phaseReport} activeAt={T_REPORT_OUT} frame={frame} />
        <ReportBox enterAt={T_REPORT_OUT} frame={frame} />
      </div>
    </AbsoluteFill>
  );
};

// Bigger-thumbnail variant of RolloutsBox tuned for the README hero: 2×2 grid
// of the first 4 ROLLOUT_VIDEOS instead of 4×2 thumbs that left the bottom
// half of the box empty.
const FlowRolloutsBox: React.FC<{ enterAt: number; frame: number }> = ({
  enterAt,
  frame,
}) => (
  <div
    style={{
      opacity: useFadeIn(frame, enterAt - 4, 14),
      background: colors.surface,
      border: `1px solid ${colors.line}`,
      borderRadius: 10,
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
    }}
  >
    <div
      style={{
        fontFamily: fonts.mono,
        fontSize: 9,
        letterSpacing: 1.6,
        color: colors.phaseRollout,
        textTransform: "uppercase",
        fontWeight: 600,
        display: "flex",
        justifyContent: "space-between",
      }}
    >
      <span>● rollouts</span>
      <span style={{ color: colors.ink4 }}>video × N</span>
    </div>
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gridTemplateRows: "repeat(2, 1fr)",
        gap: 8,
        flex: 1,
      }}
    >
      {ROLLOUT_VIDEOS.slice(0, 4).map((v, i) => {
        const delay = enterAt + i * 6;
        const op = interpolate(frame, [delay, delay + 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.22, 1, 0.36, 1),
        });
        const scale = interpolate(frame, [delay, delay + 16], [0.92, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.22, 1, 0.36, 1),
        });
        const ringColor = v.outcome === "pass" ? colors.ok : colors.err;
        return (
          <div
            key={v.src}
            style={{
              position: "relative",
              opacity: op,
              transform: `scale(${scale})`,
              borderRadius: 8,
              overflow: "hidden",
              background: colors.surface2,
              boxShadow: `0 0 0 2px ${ringColor}aa`,
            }}
          >
            <Loop durationInFrames={ROLLOUT_LOOP_FRAMES}>
              <OffthreadVideo
                src={staticFile(v.src)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                muted
              />
            </Loop>
            <div
              style={{
                position: "absolute",
                bottom: 6,
                right: 6,
                fontFamily: fonts.mono,
                fontSize: 10,
                letterSpacing: 1.0,
                padding: "2px 7px",
                borderRadius: 4,
                background: ringColor,
                color: "#fff",
                textTransform: "uppercase",
                fontWeight: 700,
              }}
            >
              {v.outcome}
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

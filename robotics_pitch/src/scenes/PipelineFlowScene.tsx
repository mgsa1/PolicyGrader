import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { colors, fonts } from "../theme";
import {
  Arrow,
  JudgesBox,
  PROMPT_TEXT,
  PromptBox,
  ReportBox,
  RolloutsBox,
} from "./PipelineScene";

// Standalone flow row, reusing the components from PipelineScene with their
// timing reset so the four boxes animate in from frame 0. Sized for a wide
// README banner (1920x500).

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
        paddingTop: 70,
        paddingLeft: 64,
        paddingRight: 64,
        paddingBottom: 40,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          letterSpacing: 2.6,
          color: colors.ink4,
          textTransform: "uppercase",
          marginBottom: 24,
        }}
      >
        Data flow · prompt → rollouts → K parallel judges → report
      </div>
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
        <RolloutsBox enterAt={T_ROLLOUTS_OUT} frame={frame} />
        <Arrow color={colors.phaseJudge} activeAt={T_JUDGES_OUT} frame={frame} />
        <JudgesBox enterAt={T_JUDGES_OUT} frame={frame} />
        <Arrow color={colors.phaseReport} activeAt={T_REPORT_OUT} frame={frame} />
        <ReportBox enterAt={T_REPORT_OUT} frame={frame} />
      </div>
    </AbsoluteFill>
  );
};

import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  OffthreadVideo,
  Loop,
  Img,
  staticFile,
  interpolate,
  Easing,
} from "remotion";
import { colors, fonts } from "../theme";
import { useFadeIn } from "../components/easing";

// 1:10–1:32 · Visual evaluation by Claude Opus 4.7, then packaged into clusters.
//
// LEFT (0–15 s): a real failed rollout video plays in a large card, looping —
//   the raw input the judge sees.
// RIGHT (0–15 s): one focal analysis card — keyframe (red dot baked in),
//   label / point / frame chips, and the actual `description` from
//   findings.jsonl. The "K = 4 parallel" chip + ramping counter
//   (47 → 3 280) at the top tells the scale story without flashing
//   keyframes or phantom cards.
// COLLAPSE → CLUSTERS (15–22 s): the focal card folds into a small thumbnail
//   on the left ("each of 3 280 analyses") while four cluster cards C1–C4
//   cascade in on the right. The story closes with: "3 280 per-rollout
//   analyses → 4 actionable clusters of failure modes." Replaces the prior
//   JudgeTrustScene; the cluster cascade is the new hero shot.

// Real failed rollout from artifacts/runs/eval_d5a040/findings.jsonl.
const ROLLOUT = {
  id: "cal_04",
  videoSrc: "rollouts/cal_04.mp4",
  keyframeSrc: "keyframes/cal_04.png", // red dot already baked into the PNG
  taxonomy: "failed_grip",
  point: [957, 1101] as const,
  frameIndex: 52,
  description:
    "Cube was lifted with the gripper but slipped free and fell back to the table.",
};
const VIDEO_LOOP_FRAMES = Math.round(2.7 * 30); // 81 frames per loop

// Counter ramp: 47 → 3 280 over the back half of Layout A. Conveys "the
// same analysis runs on all 3 280 rollouts" without rendering 3 280 cards
// or flashing the focal keyframe.
const TOTAL_TO_JUDGE = 3280;
const STATIC_JUDGED = 47;
const T_COUNTER_RAMP_START = 180; // ~6 s — start ticking once the focal card is fully revealed
const T_COUNTER_RAMP_END = 420;   // ~14 s — counter freezes just before the collapse

// Collapse → cluster reveal (Beat C+D, 15–22 s).
const T_COLLAPSE_START = 450;     // ~15 s — Layout A starts fading
const T_LAYOUT_A_HIDDEN = 490;    // ~16.3 s — Layout A fully gone
const T_LAYOUT_B_VISIBLE = 510;   // ~17 s — Layout B fully arrived
const T_CLUSTERS_HEADER = 470;    // ~15.7 s — "Packaged into…" header reveals
const T_CLUSTER_FIRST = 520;      // ~17.3 s — first cluster card lands
const CLUSTER_GAP = 12;           // frames between successive clusters

// Mini-grid sample under the focal thumbnail in Layout B — visualizes
// "synthesized from many rollouts" by stagger-filling 24 mini keyframes
// next to the focal one. Tiles are real keyframes from public/keyframes/
// (everything except cal_04, which is the focal).
const SAMPLE_KEYFRAMES = [
  "keyframes/cal_00.png", "keyframes/cal_01.png", "keyframes/cal_02.png", "keyframes/cal_03.png",
  "keyframes/cal_05.png", "keyframes/cal_06.png", "keyframes/cal_07.png", "keyframes/cal_08.png",
  "keyframes/cal_09.png", "keyframes/dep_00.png", "keyframes/dep_01.png", "keyframes/dep_02.png",
  "keyframes/dep_03.png", "keyframes/dep_04.png", "keyframes/dep_05.png", "keyframes/dep_06.png",
  "keyframes/dep_07.png", "keyframes/dep_08.png", "keyframes/dep_09.png", "keyframes/dep_10.png",
  "keyframes/dep_11.png", "keyframes/dep_12.png", "keyframes/dep_13.png", "keyframes/dep_14.png",
];
const T_GRID_FIRST = 540;         // ~18 s — first sample tile lands
const GRID_TILE_STEP = 2;         // frames between successive tile fade-ins

// Failure-mode clusters surfaced by the reporter agent. Counts kept in sync
// with the previous JudgeTrustScene clusters (deployment cohort failures).
const CLUSTERS = [
  { id: "C1", label: "missed_approach", count: 612, summary: "Open-fingers approach skims past cube" },
  { id: "C2", label: "failed_grip",     count: 388, summary: "Fingers graze cube during close — slip" },
  { id: "C3", label: "missed_approach", count: 142, summary: "Lateral overshoot at +x edge" },
  { id: "C4", label: "abstain",         count: 88,  summary: "No-contact rollouts · point = null" },
] as const;

export const JudgeAnalysisScene: React.FC = () => {
  const frame = useCurrentFrame();

  const headerOp = useFadeIn(frame, 0, 16);
  const videoOp = useFadeIn(frame, 8, 20);
  const videoX = interpolate(frame, [8, 30], [-30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // Right pane reveals in stages so the eye registers each piece.
  const T_FRAME_STRIP = 36;
  const T_KEYFRAME = T_FRAME_STRIP + 14;
  const T_BADGES = T_KEYFRAME + 16;
  const T_DESC = T_BADGES + 14;
  const T_TAGLINE = T_DESC + 18;

  const stripOp = useFadeIn(frame, T_FRAME_STRIP, 14);
  const keyframeOp = useFadeIn(frame, T_KEYFRAME, 18);
  const keyframeScale = interpolate(
    frame,
    [T_KEYFRAME, T_KEYFRAME + 22],
    [0.94, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );
  const badgesOp = useFadeIn(frame, T_BADGES, 14);
  const descOp = useFadeIn(frame, T_DESC, 18);
  const taglineOp = useFadeIn(frame, T_TAGLINE, 18);

  // Parallelism strip + counter. Static at STATIC_JUDGED until the ramp
  // window opens, then climbs to TOTAL_TO_JUDGE and freezes — "every
  // rollout, judged."
  const chipOp = useFadeIn(frame, 14, 16);
  const judgedCount = Math.round(
    interpolate(
      frame,
      [T_COUNTER_RAMP_START, T_COUNTER_RAMP_END],
      [STATIC_JUDGED, TOTAL_TO_JUDGE],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    ),
  );

  // Collapse cross-fade — Layout A (video + focal card) fades down as
  // Layout B (thumbnail + cluster cards) fades up.
  const layoutAOp = interpolate(
    frame,
    [T_COLLAPSE_START, T_LAYOUT_A_HIDDEN],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const layoutBOp = interpolate(
    frame,
    [T_COLLAPSE_START + 10, T_LAYOUT_B_VISIBLE],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const clustersHeaderOp = useFadeIn(frame, T_CLUSTERS_HEADER, 18);

  return (
    <AbsoluteFill
      style={{
        paddingTop: 124,
        paddingLeft: 64,
        paddingRight: 64,
        paddingBottom: 36,
        display: "flex",
        flexDirection: "column",
        gap: 22,
      }}
    >
      {/* Header — visible the whole 22 s */}
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
          Visual evaluation · Claude Opus 4.7
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
          Watches every frame.{" "}
          <span style={{ color: colors.err }}>Names the failure.</span>{" "}
          <span style={{ color: colors.accent }}>Points where it broke.</span>
        </div>
      </div>

      {/* Body — relative container holding both layouts. They cross-fade
          across T_COLLAPSE_START → T_LAYOUT_B_VISIBLE. */}
      <div style={{ flex: 1, position: "relative" }}>
        {/* ============================ LAYOUT A ============================
            Video left, focal analysis card (with phantom stack) right.
            Fades out during the collapse beat. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            gap: 28,
            opacity: layoutAOp,
            pointerEvents: layoutAOp > 0.05 ? "auto" : "none",
          }}
        >
          {/* LEFT: looping rollout video */}
          <div
            style={{
              flex: 1,
              opacity: videoOp,
              transform: `translateX(${videoX}px)`,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                letterSpacing: 1.8,
                color: colors.phaseRollout,
                textTransform: "uppercase",
                fontWeight: 600,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span>● input · raw rollout</span>
              <span style={{ color: colors.ink4 }}>{ROLLOUT.id}.mp4</span>
            </div>
            <div
              style={{
                flex: 1,
                borderRadius: 16,
                overflow: "hidden",
                background: "#000",
                boxShadow:
                  "0 24px 60px rgba(31,31,31,0.18), 0 0 0 1px rgba(31,31,31,0.08)",
                position: "relative",
              }}
            >
              <Loop durationInFrames={VIDEO_LOOP_FRAMES}>
                <OffthreadVideo
                  src={staticFile(ROLLOUT.videoSrc)}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  muted
                />
              </Loop>

              {/* Failure badge in the corner — visible the whole time. */}
              <div
                style={{
                  position: "absolute",
                  top: 14,
                  left: 14,
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  padding: "5px 10px",
                  borderRadius: 6,
                  background: colors.err,
                  color: "#fff",
                  fontWeight: 700,
                  letterSpacing: 1.0,
                  textTransform: "uppercase",
                }}
              >
                fail
              </div>
            </div>
          </div>

          {/* RIGHT: parallelism strip + single focal analysis card */}
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {/* Top strip: K=4 chip + running counter */}
            <div
              style={{
                opacity: chipOp,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                fontFamily: fonts.mono,
                fontSize: 12,
                letterSpacing: 1.6,
                textTransform: "uppercase",
              }}
            >
              <span style={{ color: colors.phaseJudge, fontWeight: 600 }}>
                <span style={{ marginRight: 8 }}>◆</span>
                K = 4 parallel · Claude Managed Agents
              </span>
              <span
                style={{
                  color: colors.ink3,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {judgedCount.toLocaleString("en-US")} /{" "}
                {TOTAL_TO_JUDGE.toLocaleString("en-US")} judged →
              </span>
            </div>

            {/* Focal card container */}
            <div style={{ flex: 1, position: "relative" }}>
              {/* FOCAL card */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: colors.surface,
                  border: `1px solid ${colors.phaseJudge}`,
                  borderRadius: 16,
                  padding: 26,
                  display: "flex",
                  flexDirection: "column",
                  gap: 18,
                  boxShadow: `0 0 0 4px ${colors.phaseJudge}14, 0 18px 40px rgba(31,31,31,0.08)`,
                }}
              >
                <div
                  style={{
                    fontFamily: fonts.mono,
                    fontSize: 11,
                    letterSpacing: 1.8,
                    color: colors.phaseJudge,
                    textTransform: "uppercase",
                    fontWeight: 600,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>● output · judge findings.jsonl</span>
                  <span style={{ color: colors.ink4 }}>frame {ROLLOUT.frameIndex}</span>
                </div>

                {/* Frame strip — one tick highlighted = the named failure frame. */}
                <FrameStrip
                  opacity={stripOp}
                  highlightFrac={ROLLOUT.frameIndex / 200}
                  color={colors.phaseJudge}
                />

                {/* Keyframe with the red dot already baked in. */}
                <div
                  style={{
                    opacity: keyframeOp,
                    transform: `scale(${keyframeScale})`,
                    alignSelf: "center",
                    width: 360,
                    height: 360,
                    borderRadius: 14,
                    overflow: "hidden",
                    background: "#000",
                    boxShadow: "0 8px 22px rgba(31,31,31,0.12)",
                  }}
                >
                  <Img
                    src={staticFile(ROLLOUT.keyframeSrc)}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                </div>

                {/* Label badges */}
                <div
                  style={{
                    opacity: badgesOp,
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                  }}
                >
                  <span
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 12,
                      padding: "5px 12px",
                      borderRadius: 6,
                      background: colors.errSoft,
                      border: `1px solid ${colors.err}`,
                      color: colors.err,
                      fontWeight: 600,
                    }}
                  >
                    {ROLLOUT.taxonomy}
                  </span>
                  <span
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 12,
                      padding: "5px 12px",
                      borderRadius: 6,
                      background: colors.surface2,
                      border: `1px solid ${colors.line2}`,
                      color: colors.ink2,
                    }}
                  >
                    point = ({ROLLOUT.point[0]}, {ROLLOUT.point[1]})
                  </span>
                </div>

                {/* Description quote */}
                <div
                  style={{
                    opacity: descOp,
                    fontSize: 19,
                    fontWeight: 500,
                    color: colors.ink,
                    lineHeight: 1.4,
                    letterSpacing: -0.2,
                  }}
                >
                  “{ROLLOUT.description}”
                </div>

                {/* Tagline */}
                <div
                  style={{
                    opacity: taglineOp,
                    marginTop: "auto",
                    paddingTop: 12,
                    borderTop: `1px dashed ${colors.line2}`,
                    fontFamily: fonts.mono,
                    fontSize: 12,
                    color: colors.ink3,
                    lineHeight: 1.5,
                  }}
                >
                  ↳ 2 576 px vision · per-frame walkthrough · returns{" "}
                  <code style={{ color: colors.ink2 }}>point = null</code> when
                  there&rsquo;s nothing to point at.
                </div>
              </div>
              {/* /FOCAL card */}
            </div>
            {/* /Stack */}
          </div>
          {/* /RIGHT column */}
        </div>
        {/* /LAYOUT A */}

        {/* ============================ LAYOUT B ============================
            Thumbnail left, "Packaged into 4 actionable clusters" header +
            cluster cards right. Fades in during the collapse beat. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            gap: 28,
            opacity: layoutBOp,
            pointerEvents: layoutBOp > 0.05 ? "auto" : "none",
          }}
        >
          {/* LEFT: shrunken focal analysis as "1 of 3 280" thumbnail */}
          <div
            style={{
              flex: 0.85,
              display: "flex",
              flexDirection: "column",
              gap: 14,
              justifyContent: "flex-start",
            }}
          >
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                letterSpacing: 1.8,
                color: colors.phaseJudge,
                textTransform: "uppercase",
                fontWeight: 600,
              }}
            >
              ● each of {TOTAL_TO_JUDGE.toLocaleString("en-US")} analyses
            </div>
            <div
              style={{
                width: 320,
                height: 320,
                borderRadius: 14,
                overflow: "hidden",
                background: "#000",
                border: `1px solid ${colors.phaseJudge}`,
                boxShadow: `0 0 0 4px ${colors.phaseJudge}14, 0 12px 28px rgba(31,31,31,0.10)`,
              }}
            >
              <Img
                src={staticFile(ROLLOUT.keyframeSrc)}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </div>
            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                maxWidth: 320,
              }}
            >
              <span
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  padding: "4px 10px",
                  borderRadius: 6,
                  background: colors.errSoft,
                  border: `1px solid ${colors.err}`,
                  color: colors.err,
                  fontWeight: 600,
                }}
              >
                {ROLLOUT.taxonomy}
              </span>
              <span
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  padding: "4px 10px",
                  borderRadius: 6,
                  background: colors.surface2,
                  border: `1px solid ${colors.line2}`,
                  color: colors.ink2,
                }}
              >
                frame {ROLLOUT.frameIndex}
              </span>
            </div>
            <div
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                color: colors.ink4,
                letterSpacing: 1.2,
                textTransform: "uppercase",
                marginTop: 4,
              }}
            >
              ◆ K = 4 parallel ·{" "}
              {TOTAL_TO_JUDGE.toLocaleString("en-US")} / {TOTAL_TO_JUDGE.toLocaleString("en-US")}{" "}
              judged
            </div>

            {/* Mini-grid sample: visual hint that 3 280 rollouts feed the
                final report. Tiles stagger-fill left-to-right as Layout B
                settles, mimicking the synthesis. */}
            <div style={{ marginTop: 18, width: 320 }}>
              <div
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 10,
                  letterSpacing: 1.6,
                  color: colors.ink4,
                  textTransform: "uppercase",
                  marginBottom: 8,
                }}
              >
                ◇ {SAMPLE_KEYFRAMES.length} of{" "}
                {TOTAL_TO_JUDGE.toLocaleString("en-US")} sampled · +{" "}
                {(TOTAL_TO_JUDGE - SAMPLE_KEYFRAMES.length).toLocaleString(
                  "en-US",
                )}{" "}
                more
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(8, 1fr)",
                  gap: 3,
                }}
              >
                {SAMPLE_KEYFRAMES.map((src, i) => {
                  const enterAt = T_GRID_FIRST + i * GRID_TILE_STEP;
                  const tileOp = interpolate(
                    frame,
                    [enterAt, enterAt + 6],
                    [0, 0.85],
                    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                  );
                  return (
                    <div
                      key={src}
                      style={{
                        aspectRatio: "1",
                        borderRadius: 3,
                        overflow: "hidden",
                        background: colors.surface2,
                        opacity: tileOp,
                      }}
                    >
                      <Img
                        src={staticFile(src)}
                        style={{
                          width: "100%",
                          height: "100%",
                          objectFit: "cover",
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* RIGHT: cluster cards — failure modes packaged from all analyses */}
          <div
            style={{
              flex: 1.15,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div
              style={{
                opacity: clustersHeaderOp,
                fontFamily: fonts.mono,
                fontSize: 11,
                letterSpacing: 2,
                color: colors.dep,
                textTransform: "uppercase",
                fontWeight: 600,
              }}
            >
              ● Packaged into {CLUSTERS.length} actionable clusters
            </div>

            {CLUSTERS.map((c, i) => (
              <ClusterCard
                key={c.id}
                cluster={c}
                enterAt={T_CLUSTER_FIRST + i * CLUSTER_GAP}
                frame={frame}
              />
            ))}
          </div>
        </div>
        {/* /LAYOUT B */}
      </div>
      {/* /Body */}
    </AbsoluteFill>
  );
};

const FrameStrip: React.FC<{
  opacity: number;
  highlightFrac: number;
  color: string;
}> = ({ opacity, highlightFrac, color }) => {
  const N = 16;
  const hi = Math.min(N - 1, Math.max(0, Math.round(highlightFrac * N)));
  return (
    <div style={{ display: "flex", gap: 4, opacity }}>
      {Array.from({ length: N }).map((_, i) => (
        <div
          key={i}
          style={{
            flex: 1,
            height: 6,
            borderRadius: 2,
            background: i === hi ? color : colors.line2,
          }}
        />
      ))}
    </div>
  );
};

// Cluster card — one row in the "packaged into N clusters" reveal. Slides up
// + fades in at `enterAt`. No trust-precision chip on this card; the
// calibration matrix that anchored that number was retired with the prior
// JudgeTrustScene.
const ClusterCard: React.FC<{
  cluster: { id: string; label: string; count: number; summary: string };
  enterAt: number;
  frame: number;
}> = ({ cluster, enterAt, frame }) => {
  const op = useFadeIn(frame, enterAt, 16);
  const slideY = interpolate(
    frame,
    [enterAt, enterAt + 22],
    [22, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.22, 1, 0.36, 1) },
  );

  return (
    <div
      style={{
        opacity: op,
        transform: `translateY(${slideY}px)`,
        background: colors.surface,
        border: `1px solid ${colors.line}`,
        borderRadius: 12,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 18,
      }}
    >
      <div
        style={{
          fontFamily: fonts.mono,
          fontSize: 12,
          color: colors.ink4,
          width: 32,
        }}
      >
        {cluster.id}
      </div>
      <div style={{ flex: 1 }}>
        <div
          style={{
            fontSize: 18,
            color: colors.ink,
            fontWeight: 600,
            letterSpacing: -0.3,
          }}
        >
          {cluster.summary}
        </div>
        <div
          style={{
            marginTop: 4,
            fontFamily: fonts.mono,
            fontSize: 12,
            color: colors.ink3,
          }}
        >
          {cluster.label} · {cluster.count} rollouts
        </div>
      </div>
    </div>
  );
};

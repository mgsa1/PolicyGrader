import React from "react";
import { OffthreadVideo, staticFile } from "remotion";
import { colors } from "../theme";

// Picture-in-picture face cam. The same OffthreadVideo source provides both
// the visual overlay and the primary audio for the scenes it spans, so the
// recording's voice is the audio bed while the user's webcam shows in-corner.
//
// Top-right is offset below the Topbar (top: 100) so the LIVE banner stays
// visible behind it. Source must live under public/ — Remotion serves it via
// staticFile().

export type FaceCamCorner = "tr" | "tl" | "br" | "bl";
export type FaceCamShape = "circle" | "square";

const SIZE = 320;
const SIDE_MARGIN = 32;
const TOP_OFFSET = 100; // clears the Topbar pill at top: 32, ~52 px tall
const BOTTOM_OFFSET = 32;

interface FaceCamProps {
  src?: string;
  corner?: FaceCamCorner;
  shape?: FaceCamShape;
  volume?: number;
  startFromSeconds?: number;
}

export const FaceCam: React.FC<FaceCamProps> = ({
  src = "webcam/sequences123.mov",
  corner = "tr",
  shape = "circle",
  volume = 1,
  startFromSeconds = 0,
}) => {
  const pos: React.CSSProperties = (() => {
    switch (corner) {
      case "tr":
        return { right: SIDE_MARGIN, top: TOP_OFFSET };
      case "tl":
        return { left: SIDE_MARGIN, top: TOP_OFFSET };
      case "br":
        return { right: SIDE_MARGIN, bottom: BOTTOM_OFFSET };
      case "bl":
        return { left: SIDE_MARGIN, bottom: BOTTOM_OFFSET };
    }
  })();

  const radius = shape === "circle" ? "50%" : 24;

  return (
    <div
      style={{
        position: "absolute",
        ...pos,
        width: SIZE,
        height: SIZE,
        borderRadius: radius,
        overflow: "hidden",
        background: "#000",
        boxShadow:
          "0 18px 40px rgba(0,0,0,0.28), 0 0 0 4px rgba(255,255,255,0.92), 0 0 0 5px rgba(31,31,31,0.08)",
        zIndex: 80,
      }}
    >
      <OffthreadVideo
        src={staticFile(src)}
        volume={volume}
        startFrom={Math.round(startFromSeconds * 30)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          background: colors.bg,
        }}
      />
    </div>
  );
};

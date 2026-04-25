import React from "react";
import { colors, fonts } from "../theme";

// Debug overlay marking the corner reserved for the picture-in-picture face cam.
// User picks the corner per scene; the layout of the scene must avoid placing
// load-bearing content inside this rectangle.
//
// Box is 360x360 at 1920x1080, with a 32-px outer margin matching the topbar.

export type FaceCorner = "br" | "bl" | "tr" | "tl";

const SIZE = 360;
const MARGIN = 32;

export const FaceSafeZone: React.FC<{ corner: FaceCorner }> = ({ corner }) => {
  const pos: React.CSSProperties = (() => {
    switch (corner) {
      case "br":
        return { right: MARGIN, bottom: MARGIN };
      case "bl":
        return { left: MARGIN, bottom: MARGIN };
      case "tr":
        return { right: MARGIN, top: MARGIN };
      case "tl":
        return { left: MARGIN, top: MARGIN };
    }
  })();

  return (
    <div
      style={{
        position: "absolute",
        ...pos,
        width: SIZE,
        height: SIZE,
        border: `2px dashed ${colors.accent}`,
        borderRadius: 12,
        background: "rgba(11, 95, 255, 0.06)",
        zIndex: 50,
        pointerEvents: "none",
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        padding: 12,
        fontFamily: fonts.mono,
        fontSize: 11,
        letterSpacing: 1.4,
        color: colors.accent,
        textTransform: "uppercase",
      }}
    >
      face cam · {SIZE}×{SIZE}
    </div>
  );
};

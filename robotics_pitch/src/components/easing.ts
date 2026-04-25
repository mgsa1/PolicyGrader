import { spring, interpolate, Easing } from "remotion";

export const SPRING_SOFT = {
  damping: 16,
  stiffness: 140,
  mass: 0.7,
};

export const SPRING_TIGHT = {
  damping: 22,
  stiffness: 220,
  mass: 0.6,
};

export const useFadeIn = (
  frame: number,
  start: number,
  duration = 12,
): number => {
  return interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
};

export const useSlideUp = (
  frame: number,
  start: number,
  fromY: number,
  toY: number,
  duration = 18,
): number => {
  return interpolate(frame, [start, start + duration], [fromY, toY], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
};

export { spring };

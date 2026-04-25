// Design tokens — mirrored from /tokens.css (DESIGN.md §2).
// Cohort colors are load-bearing: amber = calibration, steel-blue = deployment.

export const colors = {
  bg: "#fafafa",
  surface: "#ffffff",
  surface2: "#f1f3f4",
  ink: "#1f1f1f",
  ink2: "#3c4043",
  ink3: "#5f6368",
  ink4: "#80868b",
  line: "#e8eaed",
  line2: "#dadce0",
  accent: "#0b5fff",
  accentSoft: "#e3ecfd",

  // Cohort tokens (load-bearing)
  cal: "#b06000",
  calSoft: "#fef1d8",
  calLine: "#f5d28a",
  dep: "#1967d2",
  depSoft: "#e3ecfd",
  depLine: "#a8c7fa",

  // Semantic
  ok: "#137333",
  okSoft: "rgba(19, 115, 51, 0.10)",
  err: "#b3261e",
  errSoft: "rgba(179, 38, 30, 0.10)",
  warn: "#b06000",

  // Phase colors (for the pipeline ribbon)
  phasePlanner: "#3b82f6",
  phaseRollout: "#ec4899",
  phaseLabeling: "#f59e0b",
  phaseJudge: "#8b5cf6",
  phaseReport: "#10b981",
};

export const fonts = {
  sans: '"Inter", "Google Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
  mono: '"JetBrains Mono", "Roboto Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace',
};

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  pill: 999,
};

// Headline numbers — scaled to display $10,350 savings.
// Per-rollout rates inferred from the live dashboard "This run vs manual review"
// panel (32 scenarios, $2.87 pipeline / $120 manual, 11:32 vs 48:00):
//   pipeline = $0.090/rollout · manual = $3.75/rollout · save = $3.66/rollout
//   pipeline-time = 21.6 s/rollout · manual-time = 90 s/rollout
// Scaled to N = 2 830 scenarios so savings land at ≈ $10 350.
//
// Calibration metrics (precision / recall / clusters) are taken from the
// dashboard sample directly — they don't scale with N, they're judge accuracy.
export const numbers = {
  scenarios: 2830,
  scenariosCal: 1600,
  scenariosDep: 1230,
  pipelineCostUsd: 254,
  manualCostUsd: 10_604,
  savedUsd: 10_350,
  pipelineHours: 17,
  pipelineMinutes: 37,
  manualHours: 71,
  costDeltaPct: -98,
  timeDeltaPct: -99,
  // Calibration metrics — measured, don't scale.
  precisionPct: 91,
  precisionCiLow: 62,
  precisionCiHigh: 98,
  recallPct: 87,
  recallCiLow: 55,
  recallCiHigh: 95,
  clusters: 4,
};

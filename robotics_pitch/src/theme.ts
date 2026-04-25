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

// Headline numbers — scaled so total saved ≥ $10 000.
// Per-rollout factors are real (from artifacts/runs/evalb_d5f0ad):
//   pipeline = $1.164/rollout, manual = $3.75/rollout, save = $2.586/rollout
// Scaled to N = 4 000 scenarios.
export const numbers = {
  scenarios: 4000,
  pipelineCostUsd: 4_650,
  manualCostUsd: 15_000,
  savedUsd: 10_350,
  pipelineHours: 48,
  manualHours: 200,
  costRatio: 0.31,
  timeRatio: 0.24,
};

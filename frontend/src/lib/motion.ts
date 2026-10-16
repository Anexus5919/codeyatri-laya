// One motion system for CSS, motion/react and the 3D scene. Keep in sync with --dur-* and --ease-* in tokens.css.

export const DUR = {
  fast: 0.14,
  base: 0.24,
  slow: 0.42,
  move: 0.36,
  trace: 0.7,
} as const;

export const EASE = {
  out: [0.16, 1, 0.3, 1] as [number, number, number, number],
  inOut: [0.65, 0, 0.35, 1] as [number, number, number, number],
};

export const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3);
export const easeInOutCubic = (t: number): number => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutBack = (t: number): number => {
  const c1 = 1.4;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};
export const clamp01 = (t: number): number => (t < 0 ? 0 : t > 1 ? 1 : t);

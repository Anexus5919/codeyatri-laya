// Colours shared by the SVG boards and the 3D scene (CSS tokens cannot be read inside WebGL materials).
// Neutral board surfaces; red only marks the chosen move.

export const PAL = {
  slab: "#1a1a1d",
  cellA: "#232327",
  cellB: "#28282c",
  body: "#3fae9f",
  bodyTail: "#1f5a52",
  head: "#9ff0e2",
  eye: "#10201d",
  food: "#f0a43a",
  trace: "#ece7df",
  chosen: "#e5484d",
  other: "#8f8a83",
  cross: "#55524e",
} as const;

// 2048: cool to warm with rising luminance, so each step reads at a glance and no tile looks like the chosen-move red
const TILE: Record<number, [string, string]> = {
  2: ["#2b3037", "#cfd6de"],
  4: ["#323b46", "#dbe2e9"],
  8: ["#2e4a5d", "#e8f0f5"],
  16: ["#2a5d71", "#eef6fa"],
  32: ["#2a717e", "#f2fbfc"],
  64: ["#368477", "#f4fcf9"],
  128: ["#62935f", "#fbfdf6"],
  256: ["#a49f4f", "#1b1a13"],
  512: ["#d6af4b", "#1b1a13"],
  1024: ["#ebc96f", "#1b1a13"],
  2048: ["#f6e7b4", "#1b1a13"],
};

export function tileColors(v: number): { fill: string; text: string } {
  const c = TILE[v] ?? (v > 2048 ? ["#fbf3d9", "#1b1a13"] : ["#232327", "#ece7df"]);
  return { fill: c[0], text: c[1] };
}

// Neutral-leaning categorical colours for raw codes in an unknown grid; code 0 stays the empty floor
const CODES = ["#232327", "#6f7c86", "#63c18f", "#9a8fc9", "#e8a33d", "#4fa3b8", "#c7b38a", "#b07f6a", "#8fb06a"];

export function codeColor(code: number, order: number[]): string {
  if (code === 0) return CODES[0];
  const idx = order.indexOf(code);
  return idx >= 0 ? CODES[1 + (idx % (CODES.length - 1))] : "#555";
}

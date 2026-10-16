// Colours shared by the SVG boards and the 3D scene (CSS tokens cannot be read inside WebGL materials).

export const PAL = {
  slab: "#1a0a09",
  cellA: "#2b1512",
  cellB: "#331a16",
  body: "#cf2f37",
  bodyTail: "#6a1820",
  head: "#ff5b37",
  eye: "#f6ecdc",
  food: "#f2d6a2",
  trace: "#46d6e8",
  ember: "#ff5b37",
  ivory: "#f6ecdc",
  dim: "#7f685c",
  reject: "#ff5f7e",
} as const;

const TILE: Record<number, [string, string]> = {
  2: ["#3b1d19", "#e9d8c4"],
  4: ["#4a231d", "#f0dfca"],
  8: ["#6a281e", "#f6ecdc"],
  16: ["#86301f", "#f6ecdc"],
  32: ["#a3391f", "#fff3e3"],
  64: ["#c4441f", "#fff3e3"],
  128: ["#e2622a", "#fff7ec"],
  256: ["#ef8a3a", "#2a0d08"],
  512: ["#f6b456", "#2a0d08"],
  1024: ["#f9d58a", "#2a0d08"],
  2048: ["#fff0c6", "#2a0d08"],
};

export function tileColors(v: number): { fill: string; text: string } {
  const c = TILE[v] ?? (v > 2048 ? ["#ffffff", "#2a0d08"] : ["#2a1412", "#f6ecdc"]);
  return { fill: c[0], text: c[1] };
}

// Categorical colours for raw codes in an unknown grid; code 0 stays the empty floor
const CODES = ["#2a1412", "#6b7f8a", "#b8f53c", "#ff5f7e", "#ffb43a", "#46d6e8", "#c08cff", "#f6ecdc", "#ff8a5c"];

export function codeColor(code: number, order: number[]): string {
  if (code === 0) return CODES[0];
  const idx = order.indexOf(code);
  return idx >= 0 ? CODES[1 + (idx % (CODES.length - 1))] : "#555";
}

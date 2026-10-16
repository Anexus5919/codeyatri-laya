// Explains a recorded 2048 move as tile slides, merges and one spawned tile, so the arena can animate it.
// The plan is used only when replaying the slide on the recorded "before" board gives exactly the
// recorded "after" board plus one new 2 or 4. Otherwise the board simply switches state.

import type { Dir } from "./types";

export interface TileSprite {
  from: [number, number];
  to: [number, number];
  value: number;
  // Set on both tiles of a merge; they land on the same cell and become `mergedValue`
  mergedValue?: number;
}

export interface MovePlan {
  sprites: TileSprite[];
  spawn: { at: [number, number]; value: number } | null;
}

export function planMove(before: number[][], after: number[][], dir: Dir): MovePlan | null {
  const n = before.length;
  if (!n || after.length !== n || before.some((r) => r.length !== n) || after.some((r) => r.length !== n)) return null;
  const result: number[][] = Array.from({ length: n }, () => Array(n).fill(0));
  const sprites: TileSprite[] = [];

  for (let line = 0; line < n; line++) {
    // Cells of this row or column in the order tiles travel toward the wall they slide against
    const cells: [number, number][] = [];
    for (let k = 0; k < n; k++) {
      if (dir === "left") cells.push([line, k]);
      else if (dir === "right") cells.push([line, n - 1 - k]);
      else if (dir === "up") cells.push([k, line]);
      else cells.push([n - 1 - k, line]);
    }
    const tiles = cells.filter(([r, c]) => before[r][c] !== 0).map(([r, c]) => ({ r, c, v: before[r][c] }));
    let slot = 0;
    for (let t = 0; t < tiles.length; t++) {
      const a = tiles[t];
      const b = tiles[t + 1];
      const [tr, tc] = cells[slot];
      if (b && b.v === a.v) {
        const merged = a.v * 2;
        sprites.push({ from: [a.r, a.c], to: [tr, tc], value: a.v, mergedValue: merged });
        sprites.push({ from: [b.r, b.c], to: [tr, tc], value: b.v, mergedValue: merged });
        result[tr][tc] = merged;
        t++;
      } else {
        sprites.push({ from: [a.r, a.c], to: [tr, tc], value: a.v });
        result[tr][tc] = a.v;
      }
      slot++;
    }
  }

  let spawn: MovePlan["spawn"] = null;
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (result[r][c] === after[r][c]) continue;
      if (result[r][c] === 0 && (after[r][c] === 2 || after[r][c] === 4) && !spawn) {
        spawn = { at: [r, c], value: after[r][c] };
        continue;
      }
      return null;
    }
  }
  return { sprites, spawn };
}

export function tileHeight(v: number): number {
  return v > 0 ? 0.22 + Math.min(11, Math.log2(v)) * 0.045 : 0;
}

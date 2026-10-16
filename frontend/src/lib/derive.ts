// Pure helpers that turn logged records into what the views show. Nothing here invents a value:
// a missing field becomes null and the view says "not logged".

import type { Selection, BoardPhase } from "./store";
import type { DecisionEvent, Dir, DirMap, EnvKind, GameState, Status, StepRecord, Summary } from "./types";
import { DIRS } from "./types";

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function gameLabel(g: string | null | undefined): string {
  if (g === "snake") return "Snake";
  if (g === "2048") return "2048";
  return g ? g.charAt(0).toUpperCase() + g.slice(1) : "Unknown game";
}

export function envLabel(kind: EnvKind | undefined): string {
  if (kind === "hosted") return "Hosted arena";
  if (kind === "simulator") return "Local simulator";
  return "Environment not logged";
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "";
}

export function fmtInt(v: unknown): string {
  return isNum(v) ? Math.round(v).toLocaleString("en-US") : "n/a";
}

export function fmtP(v: unknown, digits = 3): string {
  return isNum(v) ? v.toFixed(digits) : "n/a";
}

export function fmtPct(v: unknown, digits = 1): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : "n/a";
}

export function fmtMs(v: unknown): string {
  if (!isNum(v)) return "n/a";
  return v >= 10000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v).toLocaleString("en-US")} ms`;
}

export function fmtAge(sec: unknown): string {
  if (!isNum(sec)) return "n/a";
  if (sec < 1) return "just now";
  if (sec < 60) return `${Math.round(sec)} s ago`;
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} h ago`;
  return `${Math.round(sec / 86400)} d ago`;
}

export function fmtTs(ts: unknown): string {
  if (typeof ts !== "string") return "n/a";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-GB", { hour12: false, year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const DIR_LABEL: Record<Dir, string> = { up: "Up", down: "Down", left: "Left", right: "Right" };

// What a "kind" from the facts means, worded for people; the fact text itself is always shown too
export const KIND_LABEL: Record<string, string> = {
  move: "legal move",
  eat: "eats the food",
  reach: "reaches the goal",
  wall: "wall",
  body: "hits the body",
  reverse: "reverses into the neck",
  noop: "moves no tile",
  blocked: "blocked",
  hazard: "enters a hazard",
};

const NOT_ASKED_KINDS = new Set(["reverse", "noop", "blocked", "wall"]);

// The row already names the direction, so a leading "move up: " is dropped from the logged fact.
// In the noul_nodir design that remainder is exactly the text that went into the question.
export function factBody(dir: Dir, fact: string | null): string | null {
  if (!fact) return null;
  const prefix = `move ${dir}: `;
  return fact.toLowerCase().startsWith(prefix) ? fact.slice(prefix.length) : fact;
}

export interface DirView {
  dir: Dir;
  asked: boolean | null; // null when p_true was not logged at all
  pYes: number | null;
  share: number | null;
  fact: string | null;
  kind: string | null;
  chosen: boolean;
  layaPick: boolean;
  notAskedReason: string | null;
}

export interface DecisionView {
  origin: "record" | "pending";
  i: number | null;
  step: number | null;
  result: "applied" | "rejected" | "awaiting" | "unsent" | string;
  error: string | null;
  chosen: Dir | null;
  source: string | null;
  layaChoice: Dir | null;
  reason: string | null;
  confidence: number | null;
  dirs: DirView[];
  askedCount: number;
  hasRaw: boolean;
  decideMs: number | null;
  layaMs: number | null;
  timing: StepRecord["timing"] | null;
  ts: string | null;
  eventMissing: boolean;
  nQuestions: number | null;
}

function dirViews(ev: DecisionEvent | null | undefined, probs: DirMap<number> | null | undefined, chosen: Dir | null, layaChoice: Dir | null, rejectedHere: Set<Dir>): DirView[] {
  const pTrue = ev?.p_true ?? null;
  return DIRS.map((d) => {
    const asked = pTrue ? d in pTrue : null;
    const kind = ev?.kinds?.[d] ?? null;
    const fact = ev?.facts?.[d] ?? null;
    let notAskedReason: string | null = null;
    if (asked === false) {
      if (kind && NOT_ASKED_KINDS.has(kind)) notAskedReason = `illegal move (${KIND_LABEL[kind] ?? kind})`;
      else if (rejectedHere.has(d)) notAskedReason = "rejected by the game earlier in this step";
      else notAskedReason = "no question was sent";
    }
    return {
      dir: d,
      asked,
      pYes: pTrue && isNum(pTrue[d]) ? (pTrue[d] as number) : null,
      share: probs && isNum(probs[d]) && asked !== false ? (probs[d] as number) : null,
      fact,
      kind,
      chosen: d === chosen,
      layaPick: d === layaChoice,
      notAskedReason,
    };
  });
}

function errText(e: unknown): string | null {
  if (e == null) return null;
  return typeof e === "string" ? e : JSON.stringify(e);
}

export function decisionFromRecord(r: StepRecord, records: StepRecord[]): DecisionView {
  const ev = r.event ?? null;
  const rejectedHere = new Set<Dir>();
  for (let k = r.i - 1; k >= 0 && records[k]?.step === r.step; k--) {
    if (records[k].result === "rejected") rejectedHere.add(records[k].action);
  }
  const chosen = r.action ?? null;
  const layaChoice = (ev?.laya_choice as Dir | undefined) ?? null;
  const dirs = dirViews(ev, r.probabilities ?? ev?.probabilities, chosen, layaChoice, rejectedHere);
  return {
    origin: "record",
    i: r.i,
    step: r.step,
    result: r.result,
    error: errText(r.error),
    chosen,
    source: r.source ?? ev?.source ?? null,
    layaChoice,
    reason: ev?.reason || null,
    confidence: isNum(r.confidence) ? r.confidence : null,
    dirs,
    askedCount: dirs.filter((d) => d.asked).length,
    hasRaw: !!ev?.p_true,
    decideMs: isNum(r.timing?.decide_ms) ? r.timing!.decide_ms! : ev?.decide_ms ?? null,
    layaMs: isNum(ev?.laya_ms) ? (ev!.laya_ms as number) : null,
    timing: r.timing ?? null,
    ts: r.ts ?? ev?.ts ?? null,
    eventMissing: !ev,
    nQuestions: isNum(r.n_questions) ? r.n_questions : null,
  };
}

export function decisionFromPending(ev: DecisionEvent, finished: boolean, records: StepRecord[]): DecisionView {
  const rejectedHere = new Set<Dir>();
  for (let k = records.length - 1; k >= 0 && records[k]?.step === ev.step; k--) {
    if (records[k].result === "rejected") rejectedHere.add(records[k].action);
  }
  const chosen = ev.chosen ?? null;
  const layaChoice = ev.laya_choice ?? null;
  const dirs = dirViews(ev, ev.probabilities, chosen, layaChoice, rejectedHere);
  const probs = ev.probabilities ?? {};
  return {
    origin: "pending",
    i: null,
    step: ev.step ?? null,
    result: finished ? "unsent" : "awaiting",
    error: null,
    chosen,
    source: ev.source ?? null,
    layaChoice,
    reason: ev.reason || null,
    confidence: chosen && isNum(probs[chosen]) ? (probs[chosen] as number) : null,
    dirs,
    askedCount: dirs.filter((d) => d.asked).length,
    hasRaw: !!ev.p_true,
    decideMs: ev.decide_ms ?? null,
    layaMs: ev.laya_ms ?? null,
    timing: null,
    ts: ev.ts ?? null,
    eventMissing: false,
    nQuestions: null,
  };
}

// ---------- board frames ----------

export interface BoardFrame {
  state: GameState | null;
  // The recorded move that produced `state` from `from`, used to animate exactly that move
  from: GameState | null;
  action: Dir | null;
  // Probes show a decision made ON this board (live pending decision, or history "before")
  probes: DecisionView | null;
  caption: string;
  key: string;
}

export interface Frame {
  decision: DecisionView | null;
  board: BoardFrame;
  focusIndex: number | null;
  mode: "live" | "history";
}

export interface FrameInput {
  records: StepRecord[];
  pending: DecisionEvent | null;
  status: Status | null | undefined;
  start: GameState | null;
}

export function deriveFrame(input: FrameInput, selection: Selection, phase: BoardPhase): Frame {
  const records = input.records;
  const finished = input.status === "finished";
  if (selection.mode === "history" && records[selection.i]) {
    const r = records[selection.i];
    const decision = decisionFromRecord(r, records);
    if (phase === "after") {
      return {
        mode: "history",
        focusIndex: r.i,
        decision,
        board: {
          state: r.state_after ?? null,
          from: r.state_before ?? null,
          action: r.result === "applied" ? r.action : null,
          probes: null,
          caption: `Board after line ${r.i + 1} (step ${r.step}, ${r.result})`,
          key: `h${r.i}a`,
        },
      };
    }
    const prev = records[r.i - 1];
    return {
      mode: "history",
      focusIndex: r.i,
      decision,
      board: {
        state: r.state_before ?? null,
        from: prev?.state_before ?? null,
        action: prev && prev.result === "applied" ? prev.action : null,
        probes: decision,
        caption: `Board Laya saw at step ${r.step} (line ${r.i + 1}, before the move)`,
        key: `h${r.i}b`,
      },
    };
  }
  const last = records[records.length - 1];
  const pending = input.pending ?? null;
  const pendingIsNewer = !!pending && (!last || (pending.step ?? 0) >= last.step);
  if (pending && pendingIsNewer) {
    const decision = decisionFromPending(pending, finished, records);
    return {
      mode: "live",
      focusIndex: null,
      decision,
      board: {
        state: last?.state_after ?? input.start,
        from: last?.state_before ?? null,
        action: last && last.result === "applied" ? last.action : null,
        probes: decision,
        caption: finished ? `Last decision (step ${pending.step}) was never sent` : `Deciding step ${pending.step} on this board`,
        key: `p${pending.step}-${pending.ts}`,
      },
    };
  }
  if (last) {
    return {
      mode: "live",
      focusIndex: last.i,
      decision: decisionFromRecord(last, records),
      board: {
        state: last.state_after ?? null,
        from: last.state_before ?? null,
        action: last.result === "applied" ? last.action : null,
        probes: null,
        caption: `Board after step ${last.step} (${last.result})`,
        key: `l${last.i}`,
      },
    };
  }
  return {
    mode: "live",
    focusIndex: null,
    decision: null,
    board: { state: input.start, from: null, action: null, probes: null, caption: "Starting board from the first game response", key: "start" },
  };
}

// ---------- game state readers ----------

export interface Pt {
  x: number;
  y: number;
}

export function asPt(v: unknown): Pt | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  if (isNum(o.x) && isNum(o.y)) return { x: o.x, y: o.y };
  if (isNum(o.col) && isNum(o.row)) return { x: o.col, y: o.row };
  if (Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1])) return { x: v[0], y: v[1] };
  return null;
}

export interface SnakeView {
  w: number;
  h: number;
  body: Pt[];
  food: Pt | null;
  direction: Dir | null;
  foods: number | null;
}

export function readSnake(state: GameState | null | undefined): SnakeView | null {
  if (!state) return null;
  const body = Array.isArray(state.snake) ? (state.snake as unknown[]).map(asPt).filter((p): p is Pt => !!p) : [];
  const grid = Array.isArray(state.grid) ? (state.grid as unknown[][]) : null;
  const w = isNum(state.width) ? state.width : grid?.[0]?.length ?? 0;
  const h = isNum(state.height) ? state.height : grid?.length ?? 0;
  if (!w || !h) return null;
  const dir = typeof state.direction === "string" && (DIRS as readonly string[]).includes(state.direction) ? (state.direction as Dir) : null;
  return { w, h, body, food: asPt(state.food), direction: dir, foods: isNum(state.foodEaten) ? state.foodEaten : null };
}

export function isGrid2D(v: unknown): v is number[][] {
  if (!Array.isArray(v) || v.length === 0) return false;
  const w = Array.isArray(v[0]) ? v[0].length : 0;
  if (!w) return false;
  return v.every((row) => Array.isArray(row) && row.length === w && row.every((c) => isNum(c)));
}

export function read2048(state: GameState | null | undefined): number[][] | null {
  const g = state?.grid;
  return isGrid2D(g) ? g : null;
}

export function bestTile(state: GameState | null | undefined): number | null {
  const g = read2048(state);
  if (!g) return null;
  let m = 0;
  for (const row of g) for (const v of row) m = Math.max(m, v);
  return m;
}

// Unknown games: prefer a field named grid, otherwise the first 2D numeric field, and say which one was used
export function findGrid(state: GameState | null | undefined): { key: string; grid: number[][] } | null {
  if (!state) return null;
  if (isGrid2D(state.grid)) return { key: "grid", grid: state.grid };
  for (const [k, v] of Object.entries(state)) if (isGrid2D(v)) return { key: k, grid: v };
  return null;
}

export interface Marker {
  key: string;
  label: string;
  x: number;
  y: number;
}

export function findMarkers(state: GameState | null | undefined): Marker[] {
  if (!state) return [];
  const out: Marker[] = [];
  for (const [k, v] of Object.entries(state)) {
    const p = asPt(v);
    if (p && !Array.isArray(v)) out.push({ key: k, label: k, ...p });
    else if (Array.isArray(v) && v.length && v.length <= 64 && !isGrid2D(v)) {
      v.forEach((item, idx) => {
        const q = asPt(item);
        if (q) out.push({ key: k, label: `${k}[${idx}]`, ...q });
      });
    }
  }
  return out;
}

export function scalarFields(state: GameState | null | undefined): [string, string][] {
  if (!state) return [];
  return Object.entries(state)
    .filter(([, v]) => typeof v === "number" || typeof v === "string" || typeof v === "boolean")
    .map(([k, v]) => [k, String(v)]);
}

// ---------- session-level numbers ----------

export function statusText(status: Status | undefined | null, summary: Summary | null | undefined, ageS: number | null | undefined): { label: string; detail: string } {
  switch (status) {
    case "live":
      return { label: "Live", detail: `log written ${fmtAge(ageS)}` };
    case "idle":
      return { label: "Idle", detail: `no new writes for ${Math.round(ageS ?? 0)} s, no session_end yet` };
    case "interrupted":
      return { label: "Interrupted", detail: `no session_end, last write ${fmtAge(ageS)}` };
    case "finished": {
      const won = summary?.won;
      const pts = summary?.points;
      const outcome = won === true ? "won" : won === false ? "not won" : "outcome not logged";
      return { label: won === true ? "Finished, won" : "Finished", detail: `${outcome}${isNum(pts) ? `, ${fmtInt(pts)} points` : ""}` };
    }
    default:
      return { label: "Loading", detail: "" };
  }
}

export function percentile(values: number[], q: number): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.max(0, Math.ceil(q * s.length) - 1)];
}

export function mean(values: number[]): number | null {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

export function points2048(best: number, score: number): number {
  const tilePart = best > 0 ? Math.max(0, Math.floor(Math.log2(best)) - 6) * 143 : 0;
  return Math.min(1000, tilePart + Math.floor(Math.max(0, score) / 1000));
}

export function deepEqualState(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

export function headOf(state: GameState | null | undefined): Pt | null {
  const s = readSnake(state);
  return s?.body[0] ?? null;
}

export const DELTA: Record<Dir, Pt> = { up: { x: 0, y: -1 }, down: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } };

import { useSyncExternalStore } from "react";
import type {
  DecisionEvent,
  HistoryResponse,
  SessionItem,
  StepRecord,
  VerifyResult,
} from "./types";

export type View = "arena" | "sessions" | "history" | "timing" | "audit";
export const VIEWS: readonly View[] = ["arena", "sessions", "history", "timing", "audit"];

export type Selection = { mode: "live" } | { mode: "history"; i: number; totalAtEntry: number };
export type BoardPhase = "before" | "after";
export type RendererPref = "auto" | "3d" | "2d";

export interface Feed {
  sessionId: string;
  records: StepRecord[];
  total: number;
  pending: DecisionEvent | null;
  meta: Omit<HistoryResponse, "records" | "pending" | "reset" | "after" | "next_after"> | null;
  loaded: boolean;
  complete: boolean;
  error: string | null;
}

export interface AppState {
  view: View;
  sessions: SessionItem[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
  root: string;
  followNewest: boolean;
  sessionId: string | null;
  newSessionNotice: string | null;
  feed: Feed | null;
  verify: VerifyResult | null;
  verifyFor: string | null;
  verifyAt: number | null;
  verifyBusy: boolean;
  verifyError: string | null;
  selection: Selection;
  phase: BoardPhase;
  lowMotion: boolean;
  renderer: RendererPref;
  webgl: "unknown" | "ok" | "unavailable" | "lost";
  online: boolean;
}

type Listener = () => void;

function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be blocked; the toggle still works for this page load
  }
}

function initialRenderer(): RendererPref {
  const q = new URLSearchParams(window.location.search).get("renderer");
  if (q === "svg" || q === "2d") return "2d";
  if (q === "3d" || q === "webgl") return "3d";
  const saved = readPref("laya.renderer");
  return saved === "2d" || saved === "3d" ? saved : "auto";
}

function initialLowMotion(): boolean {
  const saved = readPref("laya.motion");
  if (saved === "low") return true;
  if (saved === "full") return false;
  return prefersReducedMotion();
}

const initial: AppState = {
  view: "arena",
  sessions: [],
  sessionsLoaded: false,
  sessionsError: null,
  root: "",
  followNewest: true,
  sessionId: null,
  newSessionNotice: null,
  feed: null,
  verify: null,
  verifyFor: null,
  verifyAt: null,
  verifyBusy: false,
  verifyError: null,
  selection: { mode: "live" },
  phase: "before",
  lowMotion: initialLowMotion(),
  renderer: initialRenderer(),
  webgl: "unknown",
  online: true,
};

let state: AppState = initial;
const listeners = new Set<Listener>();

export const store = {
  get: (): AppState => state,
  set(patch: Partial<AppState> | ((s: AppState) => Partial<AppState>)): void {
    const p = typeof patch === "function" ? patch(state) : patch;
    let changed = false;
    for (const k in p) {
      if (!Object.is(state[k as keyof AppState], p[k as keyof AppState])) {
        changed = true;
        break;
      }
    }
    if (!changed) return;
    state = { ...state, ...p };
    listeners.forEach((l) => l());
  },
  subscribe(l: Listener): () => void {
    listeners.add(l);
    return () => listeners.delete(l);
  },
};

// Components subscribe to one slice; a selector must return a primitive or an existing reference
export function useStore<U>(selector: (s: AppState) => U): U {
  return useSyncExternalStore(store.subscribe, () => selector(store.get()), () => selector(initial));
}

export function enterHistory(i: number): void {
  const feed = store.get().feed;
  if (!feed || feed.records.length === 0) return;
  const clamped = Math.max(0, Math.min(feed.records.length - 1, i));
  const sel = store.get().selection;
  // Lines the server already had count as seen, even if their page is still loading
  const totalAtEntry = sel.mode === "history" ? sel.totalAtEntry : Math.max(feed.records.length, feed.total);
  store.set({ selection: { mode: "history", i: clamped, totalAtEntry } });
}

export function backToLive(): void {
  store.set({ selection: { mode: "live" }, phase: "before" });
}

export function stepBy(delta: number): void {
  const s = store.get();
  const n = s.feed?.records.length ?? 0;
  if (!n) return;
  const cur = s.selection.mode === "history" ? s.selection.i : n;
  enterHistory(cur + delta);
}

export function setLowMotion(low: boolean): void {
  writePref("laya.motion", low ? "low" : "full");
  store.set({ lowMotion: low });
}

export function setRenderer(r: RendererPref): void {
  writePref("laya.renderer", r);
  store.set({ renderer: r, webgl: store.get().webgl === "lost" ? "unknown" : store.get().webgl });
}

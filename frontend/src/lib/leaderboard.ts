// Public arena leaderboard, read through /api/leaderboard (the server fetches and caches it for 60 s).
// One poller per game, shared by the leaderboard view and the rank line on the arena page.

import { useEffect, useSyncExternalStore } from "react";

export interface LeaderboardRow {
  rank?: number;
  agentName?: string;
  score?: number;
  steps?: number;
  gameId?: string;
  timestamp?: number;
}

export interface LeaderboardData {
  game: string;
  leaderboard: LeaderboardRow[];
  fetched_at: number | null;
  stale: boolean;
  error: string | null;
  url?: string;
  local: Record<string, string>;
}

interface Entry {
  data: LeaderboardData | null;
  error: string | null;
  loading: boolean;
}

const POLL_MS = 60_000;
const entries = new Map<string, Entry>();
const users = new Map<string, number>();
const timers = new Map<string, number>();
const listeners = new Set<() => void>();
const EMPTY: Entry = { data: null, error: null, loading: false };

function emit(): void {
  listeners.forEach((l) => l());
}

async function load(game: string): Promise<void> {
  const prev = entries.get(game) ?? EMPTY;
  entries.set(game, { ...prev, loading: true });
  emit();
  try {
    const r = await fetch(`api/leaderboard?game=${encodeURIComponent(game)}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    entries.set(game, { data: (await r.json()) as LeaderboardData, error: null, loading: false });
  } catch (e) {
    // The viewer API itself is unreachable; keep whatever was shown before
    entries.set(game, { ...prev, error: e instanceof Error ? e.message : String(e), loading: false });
  }
  emit();
}

function acquire(game: string): () => void {
  users.set(game, (users.get(game) ?? 0) + 1);
  if (!timers.has(game)) {
    void load(game);
    timers.set(game, window.setInterval(() => document.visibilityState !== "hidden" && void load(game), POLL_MS));
  }
  return () => {
    const n = (users.get(game) ?? 1) - 1;
    users.set(game, n);
    if (n <= 0) {
      window.clearInterval(timers.get(game));
      timers.delete(game);
    }
  };
}

export function refreshLeaderboard(game: string): void {
  void load(game);
}

export function useLeaderboard(game: string | null | undefined): Entry {
  useEffect(() => (game ? acquire(game) : undefined), [game]);
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => (game ? entries.get(game) ?? EMPTY : EMPTY),
  );
}

export function fmtClock(sec: number | null | undefined): string {
  if (!sec) return "n/a";
  return new Date(sec * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtWhen(ms: number | null | undefined): string {
  if (!ms) return "n/a";
  return new Date(ms).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

export const OUR_AGENT = "CodeYatri";

import { useMemo } from "react";
import { deriveFrame, type Frame } from "./derive";
import { useStore } from "./store";
import type { GameState, StepRecord } from "./types";

const EMPTY: StepRecord[] = [];

export function useArenaFrame(): Frame {
  const records = useStore((s) => s.feed?.records) ?? EMPTY;
  const pending = useStore((s) => s.feed?.pending ?? null);
  const status = useStore((s) => s.feed?.meta?.status);
  const start = useStore((s) => (s.feed?.meta?.session_start?.first_response?.state as GameState | undefined) ?? null);
  const selection = useStore((s) => s.selection);
  const phase = useStore((s) => s.phase);
  return useMemo(() => deriveFrame({ records, pending, status, start }, selection, phase), [records, pending, status, start, selection, phase]);
}

export function useRecords(): StepRecord[] {
  return useStore((s) => s.feed?.records) ?? EMPTY;
}

export function decisionContext(frame: Frame, total: number, status: string | null | undefined): string {
  const d = frame.decision;
  if (!d) return "";
  if (frame.mode === "history") return `line ${(d.i ?? 0) + 1} of ${total}`;
  if (d.origin === "pending") return d.result === "awaiting" ? "deciding now" : "";
  return status === "live" ? "latest" : "";
}

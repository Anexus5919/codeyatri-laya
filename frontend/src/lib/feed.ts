// Polling engine: keeps the session list, the selected session's step records and its verification current.
// Lives outside React so a new line updates only the components that read the changed slice.

import { api, clearStepCache } from "./api";
import { store, type Feed } from "./store";

const SESSIONS_MS = 2000;
const HISTORY_MS = { live: 500, idle: 1500, interrupted: 5000, finished: 5000 } as const;
const VERIFY_MS = 6000;
const PAGE = 400;

let historyTimer: number | undefined;
let sessionsTimer: number | undefined;
let verifyTimer: number | undefined;
let token = 0;
let historyAbort: AbortController | null = null;
let started = false;
let known: Set<string> | null = null;

function hidden(): boolean {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function emptyFeed(sessionId: string): Feed {
  return { sessionId, records: [], total: 0, pending: null, meta: null, loaded: false, complete: false, error: null };
}

export function selectSession(id: string, opts: { manual?: boolean } = {}): void {
  const s = store.get();
  const patch: Parameters<typeof store.set>[0] = { newSessionNotice: null };
  if (opts.manual) {
    const newest = s.sessions[0]?.session_id;
    patch.followNewest = id === newest ? s.followNewest : false;
  }
  if (s.sessionId === id) {
    store.set(patch);
    return;
  }
  token += 1;
  historyAbort?.abort();
  clearStepCache();
  store.set({
    ...patch,
    sessionId: id,
    feed: emptyFeed(id),
    verify: null,
    verifyFor: null,
    verifyAt: null,
    verifyError: null,
    selection: { mode: "live" },
    phase: "before",
  });
  window.clearTimeout(historyTimer);
  window.clearTimeout(verifyTimer);
  void pollHistory(token);
  verifyTimer = window.setTimeout(() => void runVerify(token), 300);
}

async function pollSessions(): Promise<void> {
  window.clearTimeout(sessionsTimer);
  if (!hidden()) {
    try {
      const body = await api.sessions();
      const s = store.get();
      store.set({ sessions: body.sessions, root: body.root, sessionsLoaded: true, sessionsError: null, online: true });
      // "Newest" means a session that appeared since the last poll. Sorting by write time alone would
      // bounce between two sessions that are both being written.
      const ids = new Set(body.sessions.map((x) => x.session_id));
      const fresh = known ? body.sessions.filter((x) => !known!.has(x.session_id)) : [];
      known = ids;
      if (!s.sessionId) {
        if (body.newest) selectSession(body.newest);
      } else if (s.followNewest && fresh.length) {
        const target = fresh[0].session_id;
        // Never pull someone out of the history they are reading; offer the switch instead
        if (target !== s.sessionId) {
          if (s.selection.mode === "history") store.set({ newSessionNotice: target });
          else selectSession(target);
        }
      }
    } catch (e) {
      store.set({ sessionsError: e instanceof Error ? e.message : String(e), sessionsLoaded: true, online: false });
    }
  }
  sessionsTimer = window.setTimeout(() => void pollSessions(), SESSIONS_MS);
}

async function pollHistory(t: number): Promise<void> {
  window.clearTimeout(historyTimer);
  const s = store.get();
  const feed = s.feed;
  if (!feed || t !== token) return;
  if (hidden()) {
    historyTimer = window.setTimeout(() => void pollHistory(t), 1000);
    return;
  }
  historyAbort = new AbortController();
  let next = HISTORY_MS.live as number;
  try {
    const body = await api.history(feed.sessionId, feed.records.length, PAGE, historyAbort.signal);
    if (t !== token) return;
    const cur = store.get().feed;
    if (!cur || cur.sessionId !== body.session_id) return;
    const base = body.reset ? [] : cur.records;
    const added = body.records.filter((r) => r.i >= base.length);
    const records = added.length ? base.concat(added) : base;
    const { records: _r, pending, reset: _x, after: _a, next_after: _n, ...meta } = body;
    void _r;
    void _x;
    void _a;
    void _n;
    // Keep object identity for parts that did not change, so views keyed on them stay still
    const prev = cur.meta;
    if (prev && !body.reset) {
      const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
      if (same(prev.session_start, meta.session_start)) meta.session_start = prev.session_start;
      if (same(prev.session_end, meta.session_end)) meta.session_end = prev.session_end;
      if (same(prev.final, meta.final)) meta.final = prev.final;
      if (same(prev.summary, meta.summary)) meta.summary = prev.summary;
    }
    const complete = body.next_after >= body.total;
    const sel = store.get().selection;
    const samePending =
      !!pending && !!cur.pending && pending.step === cur.pending.step && pending.ts === cur.pending.ts && pending.chosen === cur.pending.chosen;
    store.set({
      feed: {
        ...cur,
        records,
        total: body.total,
        pending: samePending ? cur.pending : pending,
        meta,
        loaded: true,
        complete,
        error: null,
      },
      ...(body.reset && sel.mode === "history" ? { selection: { mode: "live" as const } } : {}),
      online: true,
    });
    next = complete ? HISTORY_MS[body.status] ?? 2000 : 0;
  } catch (e) {
    if (t !== token || (e instanceof DOMException && e.name === "AbortError")) return;
    const cur = store.get().feed;
    if (cur) store.set({ feed: { ...cur, error: e instanceof Error ? e.message : String(e) } });
    next = 2500;
  }
  historyTimer = window.setTimeout(() => void pollHistory(t), next);
}

export async function runVerify(t = token, force = false): Promise<void> {
  window.clearTimeout(verifyTimer);
  const s = store.get();
  const id = s.sessionId;
  if (!id || t !== token) return;
  const status = s.feed?.meta?.status;
  const settled = status === "finished" || status === "interrupted";
  const already = s.verifyFor === id && s.verify && settled && !force;
  if (!already && !hidden()) {
    store.set({ verifyBusy: true });
    try {
      const v = await api.verify(id);
      if (t !== token) return;
      store.set({ verify: v, verifyFor: id, verifyAt: Date.now(), verifyBusy: false, verifyError: null });
    } catch (e) {
      if (t !== token) return;
      store.set({ verifyBusy: false, verifyError: e instanceof Error ? e.message : String(e) });
    }
  }
  verifyTimer = window.setTimeout(() => void runVerify(t), VERIFY_MS);
}

export function recheckVerify(): void {
  void runVerify(token, true);
}

export function startFeed(): void {
  if (started) return;
  started = true;
  void pollSessions();
  document.addEventListener("visibilitychange", () => {
    if (!hidden()) {
      void pollSessions();
      void pollHistory(token);
    }
  });
}

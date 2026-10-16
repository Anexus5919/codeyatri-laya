// Hash routes: #/arena, #/sessions, #/history, #/timing, #/audit, with ?s=<session id>&i=<line index>.

import { selectSession } from "./feed";
import { enterHistory, store, VIEWS, type View } from "./store";

interface Parsed {
  view: View;
  session: string | null;
  line: number | null;
}

function parse(hash: string): Parsed {
  const raw = hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const view = (VIEWS as readonly string[]).includes(path) ? (path as View) : "arena";
  const q = new URLSearchParams(query);
  const line = q.get("i");
  return { view, session: q.get("s"), line: line !== null && /^\d+$/.test(line) ? Number(line) : null };
}

function build(view: View, session: string | null, line: number | null): string {
  const q = new URLSearchParams();
  if (session) q.set("s", session);
  if (line !== null) q.set("i", String(line));
  const qs = q.toString();
  return `#/${view}${qs ? `?${qs}` : ""}`;
}

let wantedLine: number | null = null;

export function navigate(view: View): void {
  if (store.get().view === view) return;
  store.set({ view });
}

export function initRoute(): void {
  const first = parse(window.location.hash);
  store.set({ view: first.view });
  if (first.session) selectSession(first.session, { manual: true });
  wantedLine = first.line;

  window.addEventListener("hashchange", () => {
    const p = parse(window.location.hash);
    if (p.view !== store.get().view) store.set({ view: p.view });
    if (p.session && p.session !== store.get().sessionId) selectSession(p.session, { manual: true });
  });

  let lastView = store.get().view;
  store.subscribe(() => {
    const s = store.get();
    if (wantedLine !== null && s.feed && s.feed.records.length > wantedLine) {
      const i = wantedLine;
      wantedLine = null;
      enterHistory(i);
      return;
    }
    const line = s.selection.mode === "history" ? s.selection.i : null;
    const next = build(s.view, s.followNewest ? null : s.sessionId, line);
    if (next !== window.location.hash) {
      if (s.view !== lastView) window.history.pushState(null, "", next);
      else window.history.replaceState(null, "", next);
    }
    lastView = s.view;
  });
}

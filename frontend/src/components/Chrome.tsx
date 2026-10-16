import { useEffect, useMemo, useRef, type JSX, type MouseEvent } from "react";
import { motion } from "motion/react";
import { chooseGame, chooseSource, keyOf, selectSession, sourceOf } from "../lib/feed";
import { fmtInt, gameLabel, shortId } from "../lib/derive";
import { navigate } from "../lib/route";
import { backToLive, setLowMotion, store, useStore, type View } from "../lib/store";
import { EnvBadge, StatusBadge } from "./Badges";
import { BrandMark, GameGlyph, IconArena, IconAudit, IconBack, IconBoard, IconHistory, IconMotion, IconSessions, IconTiming } from "./Glyphs";
import { VerifyChip } from "./Vitals";

const NAV: { view: View; label: string; long: string; Icon: (p: { size?: number }) => JSX.Element }[] = [
  { view: "arena", label: "Arena", long: "Live arena", Icon: IconArena },
  { view: "sessions", label: "Sessions", long: "Sessions", Icon: IconSessions },
  { view: "history", label: "History", long: "Decision history", Icon: IconHistory },
  { view: "timing", label: "Timing", long: "Timing", Icon: IconTiming },
  { view: "audit", label: "Audit", long: "Audit and verification", Icon: IconAudit },
  { view: "leaderboard", label: "Board", long: "Public arena leaderboard", Icon: IconBoard },
];

export function Rail() {
  const view = useStore((s) => s.view);
  const low = useStore((s) => s.lowMotion);
  const go = (e: MouseEvent<HTMLAnchorElement>, v: View) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    navigate(v);
  };
  return (
    <nav className="rail" aria-label="Views">
      <div className="rail-brand" title="CodeYatri">
        <BrandMark size={30} />
      </div>
      <ul className="rail-list">
        {NAV.map(({ view: v, label, long, Icon }) => (
          <li key={v}>
            <a href={`#/${v}`} className={`rail-item${view === v ? " is-active" : ""}`} aria-current={view === v ? "page" : undefined} onClick={(e) => go(e, v)} title={long}>
              {view === v ? <motion.span layoutId="rail-bead" className="rail-bead" transition={{ type: "spring", stiffness: 520, damping: 40 }} /> : null}
              <Icon size={20} />
              <span className="rail-label">{label}</span>
            </a>
          </li>
        ))}
      </ul>
      <div className="rail-foot">
        <button type="button" className={`rail-item${low ? " is-on" : ""}`} aria-pressed={low} onClick={() => setLowMotion(!low)} title={low ? "Low motion is on" : "Switch to low motion"}>
          <IconMotion size={18} low={low} />
          <span className="rail-label">{low ? "Low motion" : "Motion"}</span>
        </button>
        <a className="rail-item" href="classic" title="The original single-page viewer">
          <span className="rail-classic-mark">v1</span>
          <span className="rail-label">Classic</span>
        </a>
      </div>
    </nav>
  );
}

const STAGES = ["snake", "2048", "doom"];

function useGames(): string[] {
  const sessions = useStore((s) => s.sessions);
  return useMemo(() => {
    // The three stages always have a tab; any other game only once it has a real (non-test) session
    const real = new Set(sessions.filter((s) => sourceOf(s) === "arena").map((s) => s.game ?? "unknown"));
    const rest = [...real].filter((g) => !STAGES.includes(g)).sort();
    return [...STAGES, ...rest];
  }, [sessions]);
}

function GameSwitch() {
  const games = useGames();
  const game = useStore((s) => s.game);
  const source = useStore((s) => s.source);
  const sessions = useStore((s) => s.sessions);
  return (
    <div className="seg seg-game" role="group" aria-label="Game">
      {games.map((g) => {
        const has = sessions.some((s) => (s.game ?? "unknown") === g && sourceOf(s) === source);
        return (
          <button key={g} type="button" aria-pressed={game === g} className={has ? undefined : "is-empty"} onClick={() => chooseGame(g)} title={has ? undefined : `No ${source === "arena" ? "arena" : "simulator"} session for ${gameLabel(g)} yet`}>
            <GameGlyph game={g} size={14} />
            {gameLabel(g === "unknown" ? null : g)}
          </button>
        );
      })}
    </div>
  );
}

function SourceSwitch() {
  const source = useStore((s) => s.source);
  const doom = useStore((s) => s.game === "doom");
  return (
    <div className="seg seg-source" role="group" aria-label="Data source">
      <button type="button" aria-pressed={source === "arena"} onClick={() => chooseSource("arena")}>
        {doom ? "Real runs" : "Arena (real)"}
      </button>
      <button type="button" aria-pressed={source === "simulator"} className="is-sim" onClick={() => chooseSource("simulator")}>
        {doom ? "Test runs" : "Simulator (test)"}
      </button>
    </div>
  );
}

function usePickerRows() {
  const sessions = useStore((s) => s.sessions);
  const source = useStore((s) => s.source);
  const game = useStore((s) => s.game);
  return useMemo(() => sessions.filter((s) => sourceOf(s) === source && (s.game ?? "unknown") === game), [sessions, source, game]);
}

function SessionPicker() {
  const current = useStore((s) => s.sessionId);
  const rows = usePickerRows();
  if (rows.length < 2) return null;
  return (
    <label className="picker">
      <span className="sr-only">Session</span>
      <select value={current ?? ""} onChange={(e) => selectSession(e.target.value, { manual: true })} title="Other sessions for this game and source, newest first">
        {rows.map((s) => (
          <option key={keyOf(s)} value={keyOf(s)}>
            {shortId(s.session_id)} · {s.game === "doom" ? `${fmtInt(s.kills ?? 0)} kills` : `${fmtInt(s.points)} pts`}{s.status && s.status !== "finished" ? ` · ${s.status}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TopBar() {
  const meta = useStore((s) => s.feed?.meta ?? null);
  const sessionId = useStore((s) => s.sessionId);
  const selection = useStore((s) => s.selection);
  const total = useStore((s) => s.feed?.records.length ?? 0);
  const notice = useStore((s) => s.newSessionNotice);
  const loaded = useStore((s) => s.feed?.loaded ?? false);
  const error = useStore((s) => s.feed?.error ?? null);
  const online = useStore((s) => s.online);
  const record = useStore((s) => (s.selection.mode === "history" ? s.feed?.records[s.selection.i] : undefined));
  const verify = useStore((s) => (s.verifyFor === s.sessionId ? s.verify : null));
  const vBusy = useStore((s) => s.verifyBusy);
  const vErr = useStore((s) => s.verifyError);
  const summary = meta?.summary;
  const pickerShown = usePickerRows().length >= 2;
  const lastSeq = useRef(total);
  const pulseRef = useRef<HTMLSpanElement>(null);

  // A short ring when a new line arrives: cause and effect, never on a timer
  useEffect(() => {
    if (total > lastSeq.current && pulseRef.current && !store.get().lowMotion) {
      const el = pulseRef.current;
      el.classList.remove("is-pulsing");
      void el.offsetWidth;
      el.classList.add("is-pulsing");
    }
    lastSeq.current = total;
  }, [total]);

  return (
    <header className="topbar">
      <div className="top-left">
        <span className="brand-name">CodeYatri</span>
        <GameSwitch />
        <SourceSwitch />
        <SessionPicker />
      </div>
      <div className="top-right" aria-live="polite">
        {meta ? (
          <>
            <EnvBadge kind={summary?.env_kind} env={summary?.env} />
            {pickerShown ? null : (
              <span className="top-id mono" title={`${sessionId ?? ""}${summary?.model ? `, model ${summary.model}` : ""}${summary?.device ? ` on ${summary.device}` : ""}`}>
                {shortId(meta.session_id)}
              </span>
            )}
            <span ref={pulseRef} className="pulse-wrap">
              <StatusBadge status={meta.status} summary={summary} ageS={meta.age_s} />
            </span>
            <VerifyChip verify={verify} busy={vBusy} error={vErr} />
          </>
        ) : sessionId && !error ? (
          <span className="muted">Loading</span>
        ) : null}
        {selection.mode === "history" ? (
          <span className="history-chip">
            <span>
              Viewing step <span className="num">{record?.step ?? "?"}</span>
            </span>
            <button type="button" className="btn-live" onClick={backToLive}>
              <IconBack size={14} />
              Back to live{total > selection.totalAtEntry ? ` (+${total - selection.totalAtEntry})` : ""}
            </button>
          </span>
        ) : null}
        {!online || (error && loaded) ? (
          <span className="warn-chip" role="status">
            Connection lost, retrying
          </span>
        ) : null}
        {notice ? (
          <button type="button" className="notice" onClick={() => selectSession(notice, { manual: true })}>
            New session {shortId(notice.split("/").pop())} started, open it
          </button>
        ) : null}
      </div>
    </header>
  );
}

// Faint dot field behind everything; drifts a few pixels with the pointer unless motion is low
export function Backdrop() {
  const ref = useRef<HTMLDivElement>(null);
  const low = useStore((s) => s.lowMotion);
  useEffect(() => {
    const el = ref.current;
    if (!el || low) {
      el?.style.setProperty("--px", "0");
      el?.style.setProperty("--py", "0");
      return;
    }
    let raf = 0;
    let nx = 0;
    let ny = 0;
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      nx = (e.clientX / window.innerWidth) * 2 - 1;
      ny = (e.clientY / window.innerHeight) * 2 - 1;
      if (!raf)
        raf = requestAnimationFrame(() => {
          raf = 0;
          el.style.setProperty("--px", nx.toFixed(3));
          el.style.setProperty("--py", ny.toFixed(3));
        });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [low]);
  return <div ref={ref} className="backdrop" aria-hidden="true" />;
}

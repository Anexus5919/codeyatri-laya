import { useEffect, useRef, type JSX, type MouseEvent } from "react";
import { motion } from "motion/react";
import { selectSession } from "../lib/feed";
import { gameLabel, shortId, fmtAge } from "../lib/derive";
import { navigate } from "../lib/route";
import { backToLive, setLowMotion, store, useStore, type View } from "../lib/store";
import { EnvBadge, StatusBadge } from "./Badges";
import { VerifyChip } from "./Vitals";
import { BrandMark, GameGlyph, IconArena, IconAudit, IconBack, IconHistory, IconMotion, IconSessions, IconTiming } from "./Glyphs";

const NAV: { view: View; label: string; long: string; Icon: (p: { size?: number }) => JSX.Element }[] = [
  { view: "arena", label: "Arena", long: "Live arena", Icon: IconArena },
  { view: "sessions", label: "Sessions", long: "Sessions", Icon: IconSessions },
  { view: "history", label: "History", long: "Decision history", Icon: IconHistory },
  { view: "timing", label: "Timing", long: "Timing", Icon: IconTiming },
  { view: "audit", label: "Audit", long: "Audit and verification", Icon: IconAudit },
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
        <BrandMark size={36} />
      </div>
      <ul className="rail-list">
        {NAV.map(({ view: v, label, long, Icon }) => (
          <li key={v}>
            <a href={`#/${v}`} className={`rail-item${view === v ? " is-active" : ""}`} aria-current={view === v ? "page" : undefined} onClick={(e) => go(e, v)} title={long}>
              {view === v ? <motion.span layoutId="rail-bead" className="rail-bead" transition={{ type: "spring", stiffness: 520, damping: 40 }} /> : null}
              <Icon size={22} />
              <span className="rail-label">{label}</span>
            </a>
          </li>
        ))}
      </ul>
      <div className="rail-foot">
        <button type="button" className={`rail-item rail-toggle${low ? " is-on" : ""}`} aria-pressed={low} onClick={() => setLowMotion(!low)} title={low ? "Low motion is on" : "Switch to low motion"}>
          <IconMotion size={20} low={low} />
          <span className="rail-label">{low ? "Low motion" : "Motion"}</span>
        </button>
        <a className="rail-item rail-classic" href="classic" title="The original single-page viewer">
          <span className="rail-classic-mark mono">v1</span>
          <span className="rail-label">Classic</span>
        </a>
      </div>
    </nav>
  );
}

export function EnvBand() {
  const meta = useStore((s) => s.feed?.meta ?? null);
  if (!meta) return null;
  const kind = meta.summary?.env_kind ?? "unknown";
  const env = meta.summary?.env ?? meta.session_start?.env ?? null;
  const agent = meta.summary?.agent_name ?? meta.session_start?.agent_name ?? null;
  if (kind === "simulator")
    return (
      <div className="env-band env-band-sim" role="note">
        <strong>LOCAL SIMULATOR</strong>
        <span>test run on the local simulator, not an arena result</span>
        <span className="mono">env {env ?? "not logged"}</span>
        <span className="mono">agent {agent ?? "not logged"}</span>
      </div>
    );
  if (kind === "hosted")
    return (
      <div className="env-band env-band-hosted" role="note">
        <strong>HOSTED ARENA</strong>
        <span>real session on the arena server</span>
        <span className="mono">env {env}</span>
        <span className="mono">agent {agent ?? "not logged"}</span>
      </div>
    );
  return (
    <div className="env-band env-band-unknown" role="note">
      <strong>ENVIRONMENT NOT LOGGED</strong>
      <span>session_start has no env label, so this session cannot be shown as hosted</span>
    </div>
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
  const lastSeq = useRef(total);
  const pulseRef = useRef<HTMLSpanElement>(null);

  // A short cyan tick when a new line arrives: cause and effect, never on a timer
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
      <div className="top-brand">
        <span className="brand-name">CodeYatri</span>
        <span className="brand-sub">Laya decision arena</span>
      </div>
      <div className="top-session">
        {meta ? (
          <>
            <EnvBadge kind={summary?.env_kind} env={summary?.env} />
            <span className="top-game">
              <GameGlyph game={meta.game} size={16} />
              {gameLabel(meta.game)}
            </span>
            <span className="top-id mono" title={sessionId ?? ""}>
              {shortId(sessionId)}
            </span>
            <span className="top-model mono" title={`model ${summary?.model ?? "n/a"}${summary?.model_source ? `, source ${summary.model_source}` : ""}, device ${summary?.device ?? "n/a"}`}>
              {summary?.model ?? "model n/a"}
              {summary?.device ? ` / ${summary.device}` : ""}
            </span>
            <span ref={pulseRef} className="pulse-wrap" title={meta.status === "live" ? "Flashes cyan when a new line arrives" : undefined}>
              <StatusBadge status={meta.status} summary={summary} ageS={meta.age_s} />
            </span>
            <VerifyChip verify={verify} busy={vBusy} error={vErr} />
          </>
        ) : (
          <span className="muted">{error ? `Cannot load session: ${error}` : sessionId ? "Loading session" : online ? "Looking for sessions in the runs folder" : "API unreachable"}</span>
        )}
      </div>
      <div className="top-mode" aria-live="polite">
        {selection.mode === "history" ? (
          <>
            <span className="mode-chip mode-history">
              Viewing history: step {record?.step ?? "?"} <span className="muted mono">line {selection.i + 1} of {total}</span>
            </span>
            <button type="button" className="btn-live" onClick={backToLive}>
              <IconBack size={14} />
              Back to live{total > selection.totalAtEntry ? ` (+${total - selection.totalAtEntry})` : ""}
            </button>
          </>
        ) : loaded ? (
          <span className={`mode-chip mode-live${meta?.status === "live" ? " is-live" : ""}`}>
            {meta?.status === "live" ? "Following live" : meta?.status === "finished" ? "Showing the final logged state" : `Showing the latest logged state, last write ${fmtAge(meta?.age_s)}`}
          </span>
        ) : null}
        {!online || (error && loaded) ? (
          <span className="chip chip-warn" role="status">
            Connection to the viewer API lost, retrying. Showing the last data received.
          </span>
        ) : null}
        {notice ? (
          <button type="button" className="notice" onClick={() => selectSession(notice, { manual: true })}>
            New session {shortId(notice)} started. Open it
          </button>
        ) : null}
      </div>
    </header>
  );
}

// Faint contour field behind everything; drifts a few pixels with the pointer unless motion is low
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
  return (
    <div ref={ref} className="backdrop" aria-hidden="true">
      <svg className="backdrop-field" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice">
        <defs>
          <pattern id="bd-dots" width="28" height="28" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" fill="rgba(246,236,220,0.07)" />
          </pattern>
          <radialGradient id="bd-glow" cx="0.18" cy="0.12" r="0.7">
            <stop offset="0" stopColor="rgba(163,33,43,0.32)" />
            <stop offset="1" stopColor="rgba(163,33,43,0)" />
          </radialGradient>
        </defs>
        <rect width="1600" height="1000" fill="url(#bd-glow)" />
        <rect width="1600" height="1000" fill="url(#bd-dots)" />
        <g fill="none" stroke="rgba(255,91,55,0.07)" strokeWidth="1.2">
          {Array.from({ length: 9 }, (_, k) => (
            <ellipse key={k} cx="1240" cy="820" rx={140 + k * 95} ry={90 + k * 62} />
          ))}
        </g>
        <g fill="none" stroke="rgba(70,214,232,0.045)" strokeWidth="1">
          {Array.from({ length: 6 }, (_, k) => (
            <ellipse key={k} cx="260" cy="900" rx={120 + k * 80} ry={60 + k * 40} />
          ))}
        </g>
      </svg>
    </div>
  );
}

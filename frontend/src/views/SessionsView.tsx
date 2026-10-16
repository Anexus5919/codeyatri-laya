import { useMemo, useState } from "react";
import { EnvBadge, StatusBadge } from "../components/Badges";
import { GameGlyph } from "../components/Glyphs";
import { keyOf, selectSession, sourceOf } from "../lib/feed";
import { fmtAge, fmtInt, fmtPct, gameLabel, shortId } from "../lib/derive";
import { navigate } from "../lib/route";
import { store, useStore, type DataSource } from "../lib/store";
import type { SessionItem } from "../lib/types";

type SourceFilter = "all" | DataSource;

function outcome(s: SessionItem): string {
  if (s.status !== "finished") return "in progress or stopped";
  if (s.won === true) return "won";
  if (s.won === false) return "not won";
  return "outcome not logged";
}

export function SessionsView() {
  const sessions = useStore((s) => s.sessions);
  const loaded = useStore((s) => s.sessionsLoaded);
  const error = useStore((s) => s.sessionsError);
  const root = useStore((s) => s.root);
  const simRoots = useStore((s) => s.simRoots);
  const current = useStore((s) => s.sessionId);
  const follow = useStore((s) => s.followNewest);
  const headerSource = useStore((s) => s.source);
  const [src, setSrc] = useState<SourceFilter>(headerSource);
  const [game, setGame] = useState<string>("all");

  const games = useMemo(() => [...new Set(sessions.map((s) => s.game ?? "unknown"))], [sessions]);
  const shown = useMemo(
    () => sessions.filter((s) => (src === "all" || sourceOf(s) === src) && (game === "all" || (s.game ?? "unknown") === game)),
    [sessions, src, game],
  );
  const counts = useMemo(
    () => ({ arena: sessions.filter((s) => sourceOf(s) === "arena").length, simulator: sessions.filter((s) => sourceOf(s) === "simulator").length }),
    [sessions],
  );

  const open = (s: SessionItem) => {
    selectSession(keyOf(s), { manual: true });
    navigate("arena");
  };

  return (
    <div className="view sessions-view">
      <header className="view-head">
        <div>
          <h1>Sessions</h1>
          <p className="sub">
            Newest first. Arena sessions from <code>{root || "runs"}</code>
            {simRoots.length ? `, simulator runs from ${simRoots.length} folder${simRoots.length === 1 ? "" : "s"}` : ", no simulator folders loaded"}.
          </p>
        </div>
        <label className="switch">
          <input type="checkbox" checked={follow} onChange={(e) => store.set({ followNewest: e.target.checked })} />
          <span className="switch-track" aria-hidden="true" />
          <span>Follow new sessions</span>
        </label>
      </header>

      <div className="filters" role="group" aria-label="Filter sessions">
        <div className="seg" role="group" aria-label="Data source">
          {(["arena", "simulator", "all"] as SourceFilter[]).map((k) => (
            <button key={k} type="button" aria-pressed={src === k} onClick={() => setSrc(k)}>
              {k === "all" ? `All ${sessions.length}` : k === "arena" ? `Arena (real) ${counts.arena}` : `Simulator (test) ${counts.simulator}`}
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Game">
          <button type="button" aria-pressed={game === "all"} onClick={() => setGame("all")}>
            All games
          </button>
          {games.map((g) => (
            <button key={g} type="button" aria-pressed={game === g} onClick={() => setGame(g)}>
              {gameLabel(g === "unknown" ? null : g)}
            </button>
          ))}
        </div>
      </div>

      {error ? <p className="warn-text">Cannot reach the API: {error}</p> : null}
      {!loaded ? <p className="muted">Loading sessions</p> : null}
      {loaded && !shown.length ? <p className="muted">No sessions match these filters.</p> : null}

      <ul className="session-list">
        {shown.map((s) => (
          <li key={keyOf(s)}>
            <button type="button" className={`session-row src-${sourceOf(s)}${keyOf(s) === current ? " is-current" : ""}`} onClick={() => open(s)} aria-current={keyOf(s) === current ? "true" : undefined}>
              <span className="sr-game">
                <GameGlyph game={s.game} size={16} />
                <span>{gameLabel(s.game)}</span>
              </span>
              <span className="sr-env">
                <EnvBadge kind={s.env_kind} env={s.env} />
              </span>
              <span className="sr-id">
                <span className="mono">{shortId(s.session_id)}</span>
                <span className="small muted" title={keyOf(s)}>
                  {s.agent_name ?? "agent not logged"}, {s.model ?? "model n/a"} on {s.device ?? "n/a"}
                  {s.origin === "sim" ? `, ${keyOf(s).split("/").slice(0, -1).join("/")}` : ""}
                </span>
              </span>
              <span className="sr-status">
                <StatusBadge status={s.status} ageS={s.age_s} />
                <span className="small muted">{fmtAge(s.age_s)}</span>
              </span>
              <span className="sr-nums num">
                {fmtInt(s.steps)} moves, {fmtInt(s.rejected ?? 0)} rejected, fallback {fmtPct(s.fallback_share ?? 0)}
              </span>
              <span className="sr-outcome">
                <b className="num">{fmtInt(s.points)}</b>
                <span className="small muted">points, {outcome(s)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

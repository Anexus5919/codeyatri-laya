import { useMemo, useState } from "react";
import { EnvBadge, StatusBadge } from "../components/Badges";
import { GameGlyph } from "../components/Glyphs";
import { selectSession } from "../lib/feed";
import { fmtAge, fmtInt, fmtPct, fmtTs, gameLabel, shortId } from "../lib/derive";
import { navigate } from "../lib/route";
import { store, useStore } from "../lib/store";
import type { SessionItem } from "../lib/types";

type EnvFilter = "all" | "hosted" | "simulator";

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
  const current = useStore((s) => s.sessionId);
  const follow = useStore((s) => s.followNewest);
  const [env, setEnv] = useState<EnvFilter>("all");
  const [game, setGame] = useState<string>("all");

  const games = useMemo(() => [...new Set(sessions.map((s) => s.game ?? "unknown"))], [sessions]);
  const shown = useMemo(
    () => sessions.filter((s) => (env === "all" || s.env_kind === env) && (game === "all" || (s.game ?? "unknown") === game)),
    [sessions, env, game],
  );
  const counts = useMemo(() => ({ hosted: sessions.filter((s) => s.env_kind === "hosted").length, simulator: sessions.filter((s) => s.env_kind === "simulator").length }), [sessions]);

  const open = (id: string) => {
    selectSession(id, { manual: true });
    navigate("arena");
  };

  return (
    <div className="view sessions-view">
      <header className="view-head">
        <div>
          <h1>Sessions</h1>
          <p className="sub">
            Newest first, from <code>{root || "the runs folder"}</code> and one folder level below it.
          </p>
        </div>
        <label className="switch">
          <input type="checkbox" checked={follow} onChange={(e) => store.set({ followNewest: e.target.checked })} />
          <span className="switch-track" aria-hidden="true" />
          <span>Follow the newest session</span>
        </label>
      </header>

      <div className="filters" role="group" aria-label="Filter sessions">
        <div className="seg" role="group" aria-label="Environment">
          {(["all", "hosted", "simulator"] as EnvFilter[]).map((k) => (
            <button key={k} type="button" aria-pressed={env === k} onClick={() => setEnv(k)}>
              {k === "all" ? `All ${sessions.length}` : k === "hosted" ? `Hosted ${counts.hosted}` : `Simulator ${counts.simulator}`}
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

      {error ? <p className="callout callout-warn">Cannot reach the API: {error}</p> : null}
      {!loaded ? <p className="muted">Loading sessions...</p> : null}
      {loaded && !sessions.length ? <p className="empty-note">No sessions in this runs folder yet. Start the runner and they appear here.</p> : null}

      <ul className="session-list">
        {shown.map((s) => (
          <li key={s.session_id}>
            <button type="button" className={`session-row env-${s.env_kind ?? "unknown"}${s.session_id === current ? " is-current" : ""}`} onClick={() => open(s.session_id)} aria-current={s.session_id === current ? "true" : undefined}>
              <span className="sr-env">
                <EnvBadge kind={s.env_kind} env={s.env} />
              </span>
              <span className="sr-game">
                <GameGlyph game={s.game} size={18} />
                <span>{gameLabel(s.game)}</span>
              </span>
              <span className="sr-id">
                <span className="mono strong">{shortId(s.session_id)}</span>
                <span className="mono small muted">{s.session_id}</span>
              </span>
              <span className="sr-agent">
                <span className="small muted">agent</span>
                <span>{s.agent_name ?? "not logged"}</span>
              </span>
              <span className="sr-model">
                <span className="small muted">model / device</span>
                <span className="mono" title={s.model_source ?? undefined}>
                  {s.model ?? "n/a"} / {s.device ?? "n/a"}
                </span>
              </span>
              <span className="sr-status">
                <StatusBadge status={s.status} ageS={s.age_s} />
                <span className="small muted">{fmtAge(s.age_s)}</span>
              </span>
              <span className="sr-nums">
                <span>
                  <b className="mono">{fmtInt(s.steps)}</b> <span className="small muted">applied</span>
                </span>
                <span>
                  <b className="mono">{fmtInt(s.rejected ?? 0)}</b> <span className="small muted">rejected</span>
                </span>
                <span>
                  <b className="mono">{fmtPct(s.fallback_share ?? 0)}</b> <span className="small muted">fallback</span>
                </span>
              </span>
              <span className="sr-outcome">
                <b className="mono big">{fmtInt(s.points)}</b>
                <span className="small muted">
                  points, {outcome(s)}
                </span>
              </span>
              <span className="sr-when small muted">{s.started_ts ? `started ${fmtTs(s.started_ts)}` : ""}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

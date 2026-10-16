import { ArenaStage, RendererToggle } from "../components/ArenaStage";
import { DecisionPanel } from "../components/DecisionPanel";
import { Timeline } from "../components/Timeline";
import { StatsLine } from "../components/Vitals";
import { chooseSource, newestFor } from "../lib/feed";
import { gameLabel } from "../lib/derive";
import { decisionContext, useArenaFrame } from "../lib/hooks";
import { store, useStore } from "../lib/store";

function PhaseToggle() {
  const phase = useStore((s) => s.phase);
  return (
    <div className="seg seg-small" role="group" aria-label="Board shown for the selected line">
      <button type="button" aria-pressed={phase === "before"} onClick={() => store.set({ phase: "before" })}>
        Before move
      </button>
      <button type="button" aria-pressed={phase === "after"} onClick={() => store.set({ phase: "after" })}>
        After move
      </button>
    </div>
  );
}

function EmptyState() {
  const game = useStore((s) => s.game) ?? "snake";
  const source = useStore((s) => s.source);
  const sessions = useStore((s) => s.sessions);
  const loaded = useStore((s) => s.sessionsLoaded);
  const simRoots = useStore((s) => s.simRoots);
  if (!loaded) return <div className="view empty-view"><p className="muted">Looking for sessions</p></div>;
  const name = gameLabel(game === "unknown" ? null : game);
  const other = source === "arena" ? newestFor(sessions, "simulator", game) : newestFor(sessions, "arena", game);
  return (
    <div className="view empty-view">
      <div className="empty">
        {source === "arena" ? (
          <>
            <h1>{game === "doom" ? "No real Doom run yet." : `No arena session for ${name} yet.`}</h1>
            <p>
              {game === "2048"
                ? "It unlocks after the Snake run is verified. Real 2048 sessions appear here as soon as they are written to runs/2048."
                : game === "doom"
                  ? "Doom runs in our own copy of the engine. A run started with python -m laya_agent.doom.runner appears here as soon as it writes to runs/doom."
                  : `Real ${name} sessions appear here as soon as the runner writes them.`}
            </p>
          </>
        ) : (
          <>
            <h1>{game === "doom" ? "No Doom test run in the loaded folders." : `No simulator run for ${name} in the loaded folders.`}</h1>
            <p>{game === "doom" ? "Test runs are evaluation episodes in runs_sim_doom*, never judged results." : "Simulator runs are test runs on the local simulator, never arena results."}</p>
          </>
        )}
        <div className="empty-actions">
          {source === "arena" ? (
            <button type="button" className="btn" disabled={!other} onClick={() => chooseSource("simulator")}>
              {game === "doom" ? "View Doom test runs" : `View simulator runs for ${name}`}
            </button>
          ) : (
            <button type="button" className="btn" disabled={!other} onClick={() => chooseSource("arena")}>
              {game === "doom" ? "View real Doom runs" : `View arena sessions for ${name}`}
            </button>
          )}
        </div>
        {source === "arena" && !other && simRoots.length === 0 ? (
          <p className="muted small">
            No simulator folders are loaded. Start the viewer with <code>--sim-roots "runs_sim*"</code> to include them.
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function ArenaView() {
  const frame = useArenaFrame();
  const game = useStore((s) => s.feed?.meta?.game ?? null);
  const envKind = useStore((s) => s.feed?.meta?.summary?.env_kind);
  const status = useStore((s) => s.feed?.meta?.status);
  const total = useStore((s) => s.feed?.records.length ?? 0);
  const sessionId = useStore((s) => s.sessionId);
  const loaded = useStore((s) => s.feed?.loaded ?? false);
  const pendingText = useStore((s) => s.feed?.pending?.state_text ?? null);
  const hasFeed = useStore((s) => !!s.feed);
  const error = useStore((s) => (s.feed && !s.feed.loaded ? s.feed.error : null));
  const history = frame.mode === "history";
  const source = useStore((s) => s.source);

  if (!hasFeed) return <EmptyState />;
  if (error) {
    return (
      <div className="view empty-view">
        <div className="empty" role="alert">
          <h1>This session cannot be loaded.</h1>
          <p>The viewer API answered: {error}</p>
          <p>
            <a href="#/sessions">Choose a session</a> instead.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="view arena-view" data-env={envKind ?? "unknown"}>
      <div className="arena-main">
        <StatsLine />
        <section className="board-area" aria-label={`${gameLabel(game)} board`}>
          <div className="board-head">
            <span className="board-caption">{loaded ? frame.board.caption : "Loading the session log"}</span>
            <div className="board-tools">
              {history ? <PhaseToggle /> : null}
              <RendererToggle game={game} />
            </div>
          </div>
          <div className="board-stage">
            {envKind === "simulator" || (game === "doom" && source === "simulator") ? (
              <span className="sim-tag">{game === "doom" ? "Test run, not a judged result" : "Simulator run, not an arena result"}</span>
            ) : null}
            <ArenaStage game={game} frame={frame.board} />
          </div>
        </section>
        <Timeline />
      </div>
      <aside className="arena-side">
        <DecisionPanel decision={frame.decision} sessionId={sessionId} simulator={envKind === "simulator"} context={decisionContext(frame, total, status)} pendingText={pendingText} />
      </aside>
    </div>
  );
}

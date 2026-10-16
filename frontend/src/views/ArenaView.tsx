import { ArenaStage, RendererToggle } from "../components/ArenaStage";
import { DecisionPanel } from "../components/DecisionPanel";
import { GameGlyph } from "../components/Glyphs";
import { Timeline } from "../components/Timeline";
import { Vitals } from "../components/Vitals";
import { gameLabel } from "../lib/derive";
import { decisionContext, useArenaFrame } from "../lib/hooks";
import { store, useStore } from "../lib/store";

function PhaseToggle() {
  const phase = useStore((s) => s.phase);
  return (
    <div className="seg" role="group" aria-label="Board shown for the selected line">
      <button type="button" aria-pressed={phase === "before"} onClick={() => store.set({ phase: "before" })}>
        Before move
      </button>
      <button type="button" aria-pressed={phase === "after"} onClick={() => store.set({ phase: "after" })}>
        After move
      </button>
    </div>
  );
}

function StageLegend({ probes, trace, game }: { probes: boolean; trace: boolean; game: string | null | undefined }) {
  if (game !== "snake" && game !== "2048") return null;
  if (!probes && !(trace && game === "snake")) return null;
  return (
    <ul className="stage-legend" aria-label="Board legend">
      {probes ? (
        <li>
          <span className="lg lg-probe" aria-hidden="true" /> column height = Laya's yes-probability, ember = chosen
        </li>
      ) : null}
      {probes ? (
        <li>
          <span className="lg lg-cross" aria-hidden="true" /> cross = direction not asked
        </li>
      ) : null}
      {trace && game === "snake" ? (
        <li>
          <span className="lg lg-trace" aria-hidden="true" /> cyan line = the recorded move into this board
        </li>
      ) : null}
    </ul>
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
  const history = frame.mode === "history";
  const error = useStore((s) => (s.feed && !s.feed.loaded ? s.feed.error : null));

  if (error) {
    return (
      <div className="view">
        <div className="panel error-panel" role="alert">
          <h2>This session cannot be loaded</h2>
          <p className="sub">The viewer API answered: {error}</p>
          <p>
            <a href="#/sessions">Choose a session</a> from the runs folder instead.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="view arena-view" data-env={envKind ?? "unknown"}>
      <div className="arena-vitals">
        <Vitals />
      </div>
      <section className="stage-card" aria-label="Arena board">
        <header className="stage-head">
          <div className="stage-title">
            <GameGlyph game={game} size={18} />
            <h2>{gameLabel(game)}</h2>
            <span className="caption">{loaded ? frame.board.caption : "Loading the session log"}</span>
          </div>
          <div className="stage-tools">
            {history ? <PhaseToggle /> : null}
            <RendererToggle game={game} />
          </div>
        </header>
        <div className="stage-body">
          {envKind === "simulator" ? (
            <div className="sim-watermark" aria-hidden="true">
              SIMULATOR
            </div>
          ) : null}
          <ArenaStage game={game} frame={frame.board} />
          <StageLegend probes={!!frame.board.probes} trace={!!frame.board.action} game={game} />
        </div>
      </section>
      <div className="arena-decision">
        <DecisionPanel decision={frame.decision} sessionId={sessionId} simulator={envKind === "simulator"} context={decisionContext(frame, total, status)} pendingText={pendingText} />
      </div>
      <div className="arena-timeline">
        <Timeline />
      </div>
    </div>
  );
}

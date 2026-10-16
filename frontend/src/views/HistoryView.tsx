import { useCallback, useEffect, useState } from "react";
import { BoardSvg } from "../components/BoardSvg";
import { DecisionPanel } from "../components/DecisionPanel";
import { AppliedGlyph, DirGlyph, FallbackGlyph, RejectedGlyph } from "../components/Glyphs";
import { chosenPYes } from "../components/Timeline";
import { VirtualList } from "../components/VirtualList";
import { loadStep } from "../lib/api";
import { DIR_LABEL, fmtMs, fmtP, fmtPct } from "../lib/derive";
import { decisionContext, useArenaFrame, useRecords } from "../lib/hooks";
import { backToLive, enterHistory, store, useStore } from "../lib/store";
import type { StepDetail, StepRecord } from "../lib/types";

function ResultCell({ r }: { r: StepRecord }) {
  if (r.result === "rejected")
    return (
      <span className="cell-result c-rejected">
        <RejectedGlyph size={13} /> rejected
      </span>
    );
  if (r.source === "fallback")
    return (
      <span className="cell-result c-amber">
        <FallbackGlyph size={13} /> fallback
      </span>
    );
  return (
    <span className="cell-result c-ok" title="applied">
      <AppliedGlyph size={13} />
      <span className="sr-only">applied</span>
    </span>
  );
}

function Row({ r, sim }: { r: StepRecord; sim: boolean }) {
  const p = chosenPYes(r);
  return (
    <div className="hrow">
      <span className="h-line num">{r.i + 1}</span>
      <span className="h-step num">{r.step}</span>
      <ResultCell r={r} />
      <span className="h-move">
        <DirGlyph dir={r.action} size={14} /> {DIR_LABEL[r.action] ?? r.action}
      </span>
      <span className="h-p num" title="Laya's yes-probability for the sent move">
        {fmtP(p)}
      </span>
      <span className="h-share num" title="Share across asked moves">
        {fmtPct(r.probabilities?.[r.action])}
      </span>
      <span className="h-ms num">{fmtMs(r.timing?.decide_ms)}</span>
      <span className="h-ms num">{sim ? "sim" : fmtMs(r.timing?.api_ms)}</span>
      <span className="h-ms num">{fmtMs(r.timing?.turn_ms)}</span>
    </div>
  );
}

function LoggedLine({ sessionId, i }: { sessionId: string | null; i: number | null }) {
  const [detail, setDetail] = useState<{ key: string; data: StepDetail | null; error: string | null } | null>(null);
  const key = `${sessionId}#${i}`;
  useEffect(() => {
    if (!sessionId || i === null) return;
    let alive = true;
    loadStep(sessionId, i)
      .then((data) => alive && setDetail({ key, data, error: null }))
      .catch((e) => alive && setDetail({ key, data: null, error: String(e) }));
    return () => {
      alive = false;
    };
  }, [sessionId, i, key]);
  if (i === null) return null;
  const d = detail?.key === key ? detail : null;
  if (!d) return <p className="muted">Loading the logged line...</p>;
  if (d.error || !d.data) return <p className="warn-text">Could not load the line: {d.error}</p>;
  const line = d.data.line;
  const qs = line.decision?.questions ?? [];
  const byDir = d.data.questions_by_dir;
  return (
    <section className="logged-line" aria-label="Logged line">
      <h3>Exact questions in the submission log</h3>
      {byDir ? (
        <ol className="q-list">
          {Object.entries(byDir).map(([dir, q]) => (
            <li key={dir}>
              <span className="q-dir">{dir}</span>
              <p className="raw">{q}</p>
            </li>
          ))}
        </ol>
      ) : (
        <ol className="q-list">
          {qs.map((q, k) => (
            <li key={k}>
              <span className="q-dir">Question {k + 1}</span>
              <p className="raw">{q}</p>
            </li>
          ))}
        </ol>
      )}
      {d.data.event?.state_text ? (
        <>
          <h3>Board description sent with them</h3>
          <p className="raw">{d.data.event.state_text}</p>
        </>
      ) : null}
      <dl className="hash-row mono">
        <div>
          <dt>prev_hash</dt>
          <dd>{String(line.prev_hash ?? "n/a")}</dd>
        </div>
        <div>
          <dt>hash</dt>
          <dd>{String(line.hash ?? "n/a")}</dd>
        </div>
        <div>
          <dt>ts</dt>
          <dd>{String(line.ts ?? "n/a")}</dd>
        </div>
      </dl>
    </section>
  );
}

export function HistoryView() {
  const records = useRecords();
  const selection = useStore((s) => s.selection);
  const game = useStore((s) => s.feed?.meta?.game ?? null);
  const envKind = useStore((s) => s.feed?.meta?.summary?.env_kind);
  const status = useStore((s) => s.feed?.meta?.status);
  const sessionId = useStore((s) => s.sessionId);
  const phase = useStore((s) => s.phase);
  const frame = useArenaFrame();
  const [hover, setHover] = useState<string | null>(null);
  const onHover = useCallback((t: string | null) => setHover(t), []);
  const sel = selection.mode === "history" ? selection.i : null;
  const sim = envKind === "simulator";
  const focus = sel ?? frame.focusIndex;

  return (
    <div className="view history-view">
      <header className="view-head">
        <div>
          <h1>Decision history</h1>
          <p className="sub">Every logged line in log order. Select one to inspect it; arrow keys move, Escape returns to live.</p>
        </div>
        {sel === null ? (
          <div className="head-actions">
            <button type="button" className="btn" disabled={!records.length} onClick={() => enterHistory(records.length - 1)}>
              Inspect the latest line
            </button>
          </div>
        ) : null}
      </header>
      <div className="history-grid">
        <section className="panel hist-list" aria-label="Logged lines">
          <div className="hrow hrow-head" aria-hidden="true">
            <span className="h-line">Line</span>
            <span className="h-step">Step</span>
            <span className="cell-result">Result</span>
            <span className="h-move">Move</span>
            <span className="h-p">P(yes)</span>
            <span className="h-share">Share</span>
            <span className="h-ms">Decide</span>
            <span className="h-ms">API</span>
            <span className="h-ms">Turn</span>
          </div>
          {records.length ? (
            <VirtualList
              items={records}
              rowHeight={38}
              selected={sel}
              onSelect={(i) => enterHistory(i)}
              onKeyEscape={backToLive}
              idPrefix="hl"
              label="Logged lines, newest at the bottom"
              renderRow={(r) => <Row r={r} sim={sim} />}
            />
          ) : (
            <p className="empty-note">No lines logged yet.</p>
          )}
        </section>
        <div className="hist-detail">
          <section className="panel hist-board" aria-label="Board for the selected line">
            <header className="panel-head">
              <div>
                <h2>Board</h2>
                <p className="sub">{frame.board.caption}</p>
              </div>
              {sel !== null ? (
                <div className="seg" role="group" aria-label="Board shown">
                  <button type="button" aria-pressed={phase === "before"} onClick={() => store.set({ phase: "before" })}>
                    Before
                  </button>
                  <button type="button" aria-pressed={phase === "after"} onClick={() => store.set({ phase: "after" })}>
                    After
                  </button>
                </div>
              ) : null}
            </header>
            <div className="hist-board-svg">
              <BoardSvg game={game} frame={frame.board} onHover={onHover} />
            </div>
            {hover ? <p className="stage-hover-inline">{hover}</p> : null}
          </section>
          <section className="panel">
            <DecisionPanel decision={frame.decision} sessionId={sessionId} simulator={sim} context={decisionContext(frame, records.length, status)} />
          </section>
          <section className="panel">
            {focus !== null ? <LoggedLine sessionId={sessionId} i={focus} /> : <p className="muted">The exact questions appear once a line is logged.</p>}
          </section>
        </div>
      </div>
    </div>
  );
}

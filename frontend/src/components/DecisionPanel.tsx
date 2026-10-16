import { useEffect, useId, useState } from "react";
import { motion } from "motion/react";
import { loadStep } from "../lib/api";
import { DIR_LABEL, fmtMs, fmtP, fmtPct, KIND_LABEL } from "../lib/derive";
import type { DecisionView, DirView } from "../lib/derive";
import { DUR, EASE } from "../lib/motion";
import type { StepDetail } from "../lib/types";
import { ResultBadge, SourceBadge } from "./Badges";
import { DirGlyph, FallbackGlyph, NotAskedGlyph, RejectedGlyph } from "./Glyphs";
import { NotAskedRing, ShareBar, YesGauge } from "./Gauges";

interface Props {
  decision: DecisionView | null;
  sessionId: string | null;
  simulator: boolean;
  context: string;
  compact?: boolean;
}

function useStepDetail(sessionId: string | null, i: number | null, enabled: boolean) {
  const [state, setState] = useState<{ key: string; data: StepDetail | null; error: string | null } | null>(null);
  const key = `${sessionId}#${i}`;
  useEffect(() => {
    if (!enabled || !sessionId || i === null) return;
    let alive = true;
    loadStep(sessionId, i)
      .then((data) => alive && setState({ key, data, error: null }))
      .catch((e) => alive && setState({ key, data: null, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      alive = false;
    };
  }, [enabled, sessionId, i, key]);
  return state && state.key === key ? state : null;
}

function QuestionBlock({ sessionId, decision, dir }: { sessionId: string | null; decision: DecisionView; dir: DirView }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const pending = decision.origin === "pending";
  const detail = useStepDetail(sessionId, decision.i, open && !pending);
  const q = detail?.data?.questions_by_dir?.[dir.dir];
  return (
    <div className="question">
      <button type="button" className="link-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide exact question" : "Show exact question"}
      </button>
      {open ? (
        <div id={id} className="question-body">
          {pending ? (
            <p className="muted">The question text is written with the move line; it appears once this move is logged.</p>
          ) : !detail ? (
            <p className="muted">Loading the logged line...</p>
          ) : detail.error ? (
            <p className="warn-text">Could not load the line: {detail.error}</p>
          ) : q ? (
            <blockquote className="quote mono-quote">{q}</blockquote>
          ) : (
            <p className="muted">
              The logged questions could not be matched to directions for this line ({detail.data?.line.decision?.questions?.length ?? 0} questions, {decision.askedCount} asked
              directions). The Decision history view lists them in logged order.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}

function DirCard({ d, decision, sessionId, animKey, compact }: { d: DirView; decision: DecisionView; sessionId: string | null; animKey: string; compact: boolean }) {
  const cls = ["dir-card", d.chosen ? "is-chosen" : "", d.asked === false ? "is-not-asked" : "", d.layaPick && !d.chosen ? "is-laya-pick" : ""].filter(Boolean).join(" ");
  const label = `${DIR_LABEL[d.dir]}: ${
    d.asked === false ? `not asked, ${d.notAskedReason}` : d.pYes !== null ? `Laya's yes-probability ${fmtP(d.pYes)}, share ${fmtPct(d.share)}` : "yes-probability not logged"
  }${d.chosen ? ", chosen move" : ""}`;
  return (
    <li className={cls} aria-label={label}>
      <div className="dir-top">
        <span className="dir-id">
          <DirGlyph dir={d.dir} size={18} className="dir-glyph" />
          <span className="dir-name">{DIR_LABEL[d.dir]}</span>
        </span>
        <span className="dir-tags">
          {d.chosen ? <span className="tag tag-chosen">{decision.result === "rejected" ? "SENT, REJECTED" : "CHOSEN"}</span> : null}
          {d.layaPick && !d.chosen ? <span className="tag tag-laya">LAYA'S PICK</span> : null}
          {d.kind ? <span className="tag tag-kind" title={`kind logged for this direction: ${d.kind}`}>{KIND_LABEL[d.kind] ?? d.kind}</span> : null}
        </span>
      </div>
      <div className="dir-body">
        {d.asked === false ? (
          <>
            <NotAskedRing size={compact ? 46 : 54} />
            <div className="dir-numbers">
              <span className="not-asked-label">
                <NotAskedGlyph size={13} /> Not asked
              </span>
              <span className="dir-sub">{d.notAskedReason}</span>
            </div>
          </>
        ) : d.pYes !== null ? (
          <>
            <YesGauge p={d.pYes} chosen={d.chosen} animKey={animKey} size={compact ? 46 : 54} />
            <div className="dir-numbers">
              <span className="pyes mono">{fmtP(d.pYes)}</span>
              <span className="dir-sub">Laya's yes-probability</span>
              <span className="dir-share mono">{fmtPct(d.share)} share of asked moves</span>
            </div>
          </>
        ) : (
          <div className="dir-numbers">
            <span className="dir-sub">Raw yes-probability not logged for this line{d.share !== null ? `; logged share ${fmtPct(d.share)}` : ""}</span>
          </div>
        )}
      </div>
      {d.fact ? (
        <blockquote className="quote fact" title="Fact text written for this direction (decision event)">
          {d.fact}
        </blockquote>
      ) : (
        <p className="muted small">No fact text logged for this direction.</p>
      )}
      {d.asked ? <QuestionBlock sessionId={sessionId} decision={decision} dir={d} /> : null}
    </li>
  );
}

function ContextBlock({ sessionId, decision, pendingText }: { sessionId: string | null; decision: DecisionView; pendingText: string | null }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const detail = useStepDetail(sessionId, decision.i, open && decision.origin === "record");
  const text = decision.origin === "pending" ? pendingText : detail?.data?.event?.state_text;
  return (
    <div className="context">
      <button type="button" className="link-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide board description sent to Laya" : "Board description sent to Laya"}
      </button>
      {open ? (
        <div id={id}>
          {text ? (
            <blockquote className="quote mono-quote">{text}</blockquote>
          ) : decision.origin === "record" && !detail ? (
            <p className="muted">Loading the logged event...</p>
          ) : (
            <p className="muted">No board description logged for this decision.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export function DecisionPanel({ decision, sessionId, simulator, context, compact = false, pendingText = null }: Props & { pendingText?: string | null }) {
  if (!decision) {
    return (
      <section className="panel decision is-empty" aria-label="Decision">
        <header className="panel-head">
          <h2>Decision</h2>
        </header>
        <p className="empty-note">No decision logged yet for this session. The first decision appears here as soon as the runner writes it.</p>
      </section>
    );
  }
  const animKey = `${decision.origin}-${decision.i ?? "p"}-${decision.step}-${decision.ts}`;
  const fallback = decision.source === "fallback";
  const t = decision.timing;
  return (
    <section className={`panel decision${fallback ? " is-fallback" : ""}${compact ? " is-compact" : ""}`} aria-labelledby={`dec-${animKey}`}>
      <header className="panel-head">
        <div>
          <h2 id={`dec-${animKey}`}>
            Decision <span className="mono step-no">step {decision.step ?? "n/a"}</span>
          </h2>
          <p className="sub">{context}</p>
        </div>
        <div className="badges">
          <SourceBadge source={decision.source} large={fallback} />
          <ResultBadge result={decision.result} />
        </div>
      </header>

      {fallback ? (
        <div className="callout callout-fallback" role="note">
          <FallbackGlyph size={18} />
          <div>
            <strong>Fallback move, not Laya's pick.</strong>{" "}
            {decision.layaChoice ? (
              <>
                Laya ranked <b>{DIR_LABEL[decision.layaChoice]}</b> highest; the runner sent <b>{decision.chosen ? DIR_LABEL[decision.chosen] : "n/a"}</b>.
              </>
            ) : null}
            <div className="reason">Logged reason: {decision.reason ? <q>{decision.reason}</q> : <span className="muted">none logged</span>}</div>
          </div>
        </div>
      ) : null}
      {decision.result === "rejected" ? (
        <div className="callout callout-reject" role="note">
          <RejectedGlyph size={18} />
          <div>
            <strong>The game rejected this move.</strong> Server error: {decision.error ? <q>{decision.error}</q> : <span className="muted">not logged</span>}. The runner asks Laya again without it.
          </div>
        </div>
      ) : null}
      {decision.eventMissing ? (
        <p className="callout callout-info">No matching decision event for this line, so raw yes-probabilities and facts are unavailable. The values below come from the submission log.</p>
      ) : null}

      {/* Keyed per decision so it settles in once; no exit phase, so fast live updates never leave it blank */}
      <motion.div
        key={animKey}
        className="decision-body"
        initial={{ opacity: 0.4, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: DUR.base, ease: EASE.out }}
      >
          <p className="method">
            Each asked direction is one yes/no question to Laya. The big number is Laya's yes-probability for that move, not a chance of winning.
          </p>
          <ShareBar dirs={decision.dirs} animKey={animKey} />
          <ol className="dir-list">
            {decision.dirs.map((d) => (
              <DirCard key={d.dir} d={d} decision={decision} sessionId={sessionId} animKey={animKey} compact={compact} />
            ))}
          </ol>
      </motion.div>

      <footer className="decision-foot">
        <dl className="dec-timing">
          <div>
            <dt>Decide</dt>
            <dd className="mono">{fmtMs(t?.decide_ms ?? decision.decideMs)}</dd>
          </div>
          <div>
            <dt>Laya call</dt>
            <dd className="mono">{fmtMs(decision.layaMs)}</dd>
          </div>
          <div>
            <dt>Game API</dt>
            <dd className="mono">{t ? (simulator ? "local simulator" : fmtMs(t.api_ms)) : "pending"}</dd>
          </div>
          <div>
            <dt>Turn</dt>
            <dd className="mono">{t ? fmtMs(t.turn_ms) : "pending"}</dd>
          </div>
        </dl>
        <ContextBlock sessionId={sessionId} decision={decision} pendingText={pendingText} />
      </footer>
    </section>
  );
}

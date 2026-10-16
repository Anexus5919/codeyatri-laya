import { useEffect, useId, useState } from "react";
import { motion } from "motion/react";
import { loadStep } from "../lib/api";
import { DIR_LABEL, factBody, fmtMs, fmtP } from "../lib/derive";
import type { DecisionView, DirView } from "../lib/derive";
import { DUR, EASE } from "../lib/motion";
import type { StepDetail } from "../lib/types";
import { DecisionLine } from "./Badges";
import { DirGlyph } from "./Glyphs";

interface Props {
  decision: DecisionView | null;
  sessionId: string | null;
  simulator: boolean;
  context?: string;
  pendingText?: string | null;
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

// Whole percent reads calmly, but never round 99.6% up to 100% or 0.4% down to 0%
const pct = (v: number | null) => {
  if (v === null) return "";
  const p = v * 100;
  const text = p > 0 && p < 1 ? p.toFixed(1) : p > 99 && p < 100 ? p.toFixed(1) : String(Math.round(p));
  return `${text}% share`;
};

function DirRow({ d, animKey }: { d: DirView; animKey: string }) {
  const fact = factBody(d.dir, d.fact);
  const notAsked = d.asked === false;
  const label = `${DIR_LABEL[d.dir]}: ${notAsked ? `not asked, ${d.notAskedReason}` : d.pYes !== null ? `yes-probability ${fmtP(d.pYes)}` : "yes-probability not logged"}${d.chosen ? ", chosen" : ""}`;
  return (
    <li className={`dir${d.chosen ? " is-chosen" : ""}${notAsked ? " is-not-asked" : ""}${d.layaPick && !d.chosen ? " is-laya-pick" : ""}`} aria-label={label}>
      <div className="dir-head">
        <DirGlyph dir={d.dir} size={15} className="dir-glyph" />
        <span className="dir-name">{DIR_LABEL[d.dir]}</span>
        {notAsked ? (
          <span className="dir-na">Not asked</span>
        ) : d.pYes !== null ? (
          <>
            <span className="dir-p num">{fmtP(d.pYes)}</span>
            <span className="dir-share num">{pct(d.share)}</span>
          </>
        ) : (
          <span className="dir-na">Not logged</span>
        )}
      </div>
      {!notAsked && d.pYes !== null ? (
        <div className="pbar" aria-hidden="true">
          <motion.span
            key={animKey}
            className="pbar-fill"
            initial={{ scaleX: 0 }}
            animate={{ scaleX: Math.max(0, Math.min(1, d.pYes)) }}
            transition={{ duration: DUR.slow, ease: EASE.out }}
          />
        </div>
      ) : null}
      <p className="dir-fact">{fact ?? (notAsked ? d.notAskedReason : "No fact logged")}</p>
      {d.layaPick && !d.chosen ? <p className="dir-note">Laya ranked this highest</p> : null}
    </li>
  );
}

function Questions({ sessionId, decision, pendingText }: { sessionId: string | null; decision: DecisionView; pendingText: string | null }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const pending = decision.origin === "pending";
  const detail = useStepDetail(sessionId, decision.i, open && !pending);
  const byDir = detail?.data?.questions_by_dir ?? null;
  const all = detail?.data?.line.decision?.questions ?? [];
  const stateText = pending ? pendingText : detail?.data?.event?.state_text;
  return (
    <div className="questions">
      <button type="button" className="disclosure" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        <span className="disclosure-mark" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
        Questions sent to Laya
      </button>
      {open ? (
        <div id={id} className="questions-body">
          {pending ? (
            <p className="muted">The question text is written with the move line; it appears once this move is logged.</p>
          ) : !detail ? (
            <p className="muted">Loading the logged line</p>
          ) : detail.error ? (
            <p className="warn-text">Could not load the line: {detail.error}</p>
          ) : (
            <ol className="q-list">
              {byDir
                ? Object.entries(byDir).map(([dir, q]) => (
                    <li key={dir}>
                      <span className="q-dir">{DIR_LABEL[dir as keyof typeof DIR_LABEL]}</span>
                      <p className="raw">{q}</p>
                    </li>
                  ))
                : all.map((q, k) => (
                    <li key={k}>
                      <span className="q-dir">Question {k + 1}</span>
                      <p className="raw">{q}</p>
                    </li>
                  ))}
            </ol>
          )}
          {stateText ? (
            <div className="q-state">
              <span className="q-dir">Board description</span>
              <p className="raw">{stateText}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function DecisionPanel({ decision, sessionId, simulator, context, pendingText = null }: Props) {
  if (!decision) {
    return (
      <section className="decision is-empty" aria-label="Decision">
        <h2 className="decision-title">Decision</h2>
        <p className="muted">No decision logged yet. The first one appears here as soon as the runner writes it.</p>
      </section>
    );
  }
  const animKey = `${decision.origin}-${decision.i ?? "p"}-${decision.step}-${decision.ts}`;
  const t = decision.timing;
  const timing = [
    ["Decide", fmtMs(t?.decide_ms ?? decision.decideMs)],
    ["Laya", fmtMs(decision.layaMs)],
    ["Game API", t ? (simulator ? "local simulator" : fmtMs(t.api_ms)) : "pending"],
    ["Turn", t ? fmtMs(t.turn_ms) : "pending"],
  ];
  return (
    <section className={`decision${decision.source === "fallback" ? " is-fallback" : ""}`} aria-labelledby={`dec-${animKey}`}>
      <header className="decision-head">
        <h2 id={`dec-${animKey}`} className="decision-title">
          Step <span className="num">{decision.step ?? "n/a"}</span>
        </h2>
        {context ? <span className="decision-context">{context}</span> : null}
      </header>
      <DecisionLine decision={decision} />
      {decision.source === "fallback" && decision.reason ? <p className="decision-reason">{decision.reason}</p> : null}
      {decision.result === "rejected" && decision.error ? <p className="decision-reason">Game said: {decision.error}</p> : null}
      {decision.eventMissing ? <p className="decision-reason">No matching decision event, so yes-probabilities and facts are unavailable for this line.</p> : null}
      <p className="decision-help">P(yes) is Laya's answer to one yes/no question per move, not a chance of winning.</p>
      <motion.ol
        key={animKey}
        className="dir-list"
        initial={{ opacity: 0.4 }}
        animate={{ opacity: 1 }}
        transition={{ duration: DUR.base, ease: EASE.out }}
      >
        {decision.dirs.map((d) => (
          <DirRow key={d.dir} d={d} animKey={animKey} />
        ))}
      </motion.ol>
      <Questions sessionId={sessionId} decision={decision} pendingText={pendingText} />
      <p className="decision-timing num">
        {timing.map(([k, v], n) => (
          <span key={k}>
            {n ? <span className="sep" aria-hidden="true"> · </span> : null}
            {k} {v}
          </span>
        ))}
      </p>
    </section>
  );
}

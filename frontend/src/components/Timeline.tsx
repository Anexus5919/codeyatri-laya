// Step ribbon: every logged line as one mark. Shape carries the meaning (bar = applied by Laya,
// triangle = fallback, cross = rejected), height = Laya's yes-probability for the move that was sent.

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as RPointerEvent } from "react";
import { DIR_LABEL, fmtP } from "../lib/derive";
import { backToLive, enterHistory, stepBy, useStore } from "../lib/store";
import type { StepRecord } from "../lib/types";
import { AppliedGlyph, FallbackGlyph, IconChevron, IconLive, PendingGlyph, RejectedGlyph } from "./Glyphs";

const H = 74;
const BASE = 46;
const MAXH = 34;
const PAD = 8;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cw = Math.round(entries[0].contentRect.width);
      if (cw > 0) setW(cw);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, w };
}

export function chosenPYes(r: StepRecord): number | null {
  const v = r.event?.p_true?.[r.action];
  return typeof v === "number" ? v : null;
}

export function describeRecord(r: StepRecord): string {
  const p = chosenPYes(r);
  return `line ${r.i + 1}, step ${r.step}, ${DIR_LABEL[r.action] ?? r.action}, ${r.result}, ${r.source === "fallback" ? "fallback" : "Laya"}${p !== null ? `, yes-probability ${fmtP(p)}` : ""}`;
}

export function Timeline() {
  const records = useStore((s) => s.feed?.records) ?? EMPTY;
  const pending = useStore((s) => s.feed?.pending ?? null);
  const status = useStore((s) => s.feed?.meta?.status);
  const selection = useStore((s) => s.selection);
  const { ref, w } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const dragging = useRef(false);
  const n = records.length;
  const span = Math.max(1, w - PAD * 2);
  const xOf = useCallback((i: number) => PAD + ((i + 0.5) / Math.max(1, n)) * span, [n, span]);

  const paths = useMemo(() => {
    let applied = "";
    let fallback = "";
    let rejected = "";
    let unknown = "";
    const bw = Math.max(0.6, Math.min(5, (span / Math.max(1, n)) * 0.62));
    for (const r of records) {
      const x = xOf(r.i);
      const p = chosenPYes(r);
      if (r.result === "rejected") {
        const s = Math.max(2.2, Math.min(4, bw));
        rejected += `M${x - s} ${BASE + 6} L${x + s} ${BASE + 6 + 2 * s} M${x + s} ${BASE + 6} L${x - s} ${BASE + 6 + 2 * s} `;
      } else if (r.source === "fallback") {
        const s = Math.max(3, Math.min(5, bw * 1.2));
        fallback += `M${x} ${BASE - 2 - (p ?? 0.5) * MAXH - 2 * s} L${x + s} ${BASE - 2 - (p ?? 0.5) * MAXH} L${x - s} ${BASE - 2 - (p ?? 0.5) * MAXH} Z `;
        applied += `M${x - bw / 2} ${BASE} h${bw} v${-(p ?? 0.5) * MAXH} h${-bw} Z `;
      } else if (p === null) {
        unknown += `M${x - bw / 2} ${BASE} h${bw} v-6 h${-bw} Z `;
      } else {
        applied += `M${x - bw / 2} ${BASE} h${bw} v${-Math.max(1, p * MAXH)} h${-bw} Z `;
      }
    }
    return { applied, fallback, rejected, unknown };
  }, [records, xOf, span, n]);

  const sel = selection.mode === "history" ? selection.i : null;
  const indexAt = useCallback(
    (clientX: number) => {
      const el = ref.current;
      if (!el || !n) return null;
      const r = el.getBoundingClientRect();
      const t = (clientX - r.left - PAD) / span;
      return Math.max(0, Math.min(n - 1, Math.floor(t * n)));
    },
    [n, span, ref],
  );

  const onDown = (e: RPointerEvent<HTMLDivElement>) => {
    const i = indexAt(e.clientX);
    if (i === null) return;
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    enterHistory(i);
  };
  const onMove = (e: RPointerEvent<HTMLDivElement>) => {
    const i = indexAt(e.clientX);
    setHover(i);
    if (dragging.current && i !== null) enterHistory(i);
  };
  const onUp = () => {
    dragging.current = false;
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const map: Record<string, () => void> = {
      ArrowLeft: () => stepBy(-1),
      ArrowRight: () => stepBy(1),
      ArrowDown: () => stepBy(-1),
      ArrowUp: () => stepBy(1),
      PageDown: () => stepBy(-10),
      PageUp: () => stepBy(10),
      Home: () => enterHistory(0),
      End: () => backToLive(),
      Escape: () => backToLive(),
    };
    const fn = map[e.key];
    if (fn) {
      e.preventDefault();
      fn();
    }
  };

  const hovered = hover !== null ? records[hover] : null;
  const selRec = sel !== null ? records[sel] : null;
  const liveText = n ? `Following live, latest line ${n}${pending && status !== "finished" ? `, deciding step ${pending.step}` : ""}` : "No lines logged yet";
  const totalAtEntry = selection.mode === "history" ? selection.totalAtEntry : n;
  const newSince = Math.max(0, n - totalAtEntry);

  return (
    <section className="timeline" aria-label="Step timeline">
      <div className="timeline-head">
        <div className="timeline-title">
          <h2>Timeline</h2>
          <span className="sub mono">{n ? `${n} logged lines` : "waiting for lines"}</span>
        </div>
        <div className="timeline-controls">
          <button type="button" className="icon-btn" onClick={() => stepBy(-1)} disabled={!n || sel === 0} aria-label="Previous line">
            <IconChevron dir="left" />
          </button>
          <button type="button" className="icon-btn" onClick={() => stepBy(1)} disabled={!n || sel === null} aria-label="Next line">
            <IconChevron dir="right" />
          </button>
          <button type="button" className={`btn-live${sel === null ? " is-live" : ""}`} onClick={backToLive} disabled={sel === null} aria-label={sel === null ? "Following live" : "Back to live"}>
            <IconLive size={14} />
            <span>{sel === null ? "Following live" : `Back to live${newSince ? ` (+${newSince} new)` : ""}`}</span>
          </button>
        </div>
      </div>
      <div
        ref={ref}
        className="ribbon"
        role="slider"
        tabIndex={0}
        aria-label="Logged lines. Arrow keys move one line, Page keys ten, Home goes to the first line, End or Escape returns to live"
        aria-valuemin={1}
        aria-valuemax={Math.max(1, n)}
        aria-valuenow={sel !== null ? sel + 1 : n}
        aria-valuetext={selRec ? `Viewing history: ${describeRecord(selRec)}` : liveText}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKey}
      >
        <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} aria-hidden="true" focusable="false">
          <line x1={PAD} x2={w - PAD} y1={BASE + 0.5} y2={BASE + 0.5} className="rb-base" />
          <line x1={PAD} x2={w - PAD} y1={BASE - MAXH * 0.5} y2={BASE - MAXH * 0.5} className="rb-half" />
          <path d={paths.applied} className="rb-applied" />
          <path d={paths.unknown} className="rb-unknown" />
          <path d={paths.fallback} className="rb-fallback" />
          <path d={paths.rejected} className="rb-rejected" />
          {hover !== null && n ? <line x1={xOf(hover)} x2={xOf(hover)} y1={4} y2={H - 4} className="rb-hover" /> : null}
          {sel !== null && n ? (
            <g className="rb-sel">
              <line x1={xOf(sel)} x2={xOf(sel)} y1={2} y2={H - 2} />
              <circle cx={xOf(sel)} cy={BASE} r={4.5} />
            </g>
          ) : n ? (
            <g className="rb-now">
              <line x1={w - PAD} x2={w - PAD} y1={2} y2={H - 2} />
            </g>
          ) : null}
        </svg>
        {hovered ? (
          <div className="rb-tip mono" style={{ left: Math.min(Math.max(xOf(hovered.i), 90), w - 90) }}>
            {describeRecord(hovered)}
          </div>
        ) : null}
      </div>
      <ul className="legend" aria-label="Timeline legend">
        <li>
          <span className="lg lg-applied" aria-hidden="true" /> <AppliedGlyph size={12} /> applied, bar height = Laya's yes-probability of the sent move
        </li>
        <li>
          <FallbackGlyph size={12} className="c-amber" /> fallback move
        </li>
        <li>
          <RejectedGlyph size={12} className="c-reject" /> rejected by the game
        </li>
        <li>
          <span className="lg lg-half" aria-hidden="true" /> dashed guide = 0.5
        </li>
        {pending && status !== "finished" ? (
          <li>
            <PendingGlyph size={12} className="c-ember" /> step {pending.step} decided, awaiting the game
          </li>
        ) : null}
      </ul>
    </section>
  );
}

const EMPTY: StepRecord[] = [];

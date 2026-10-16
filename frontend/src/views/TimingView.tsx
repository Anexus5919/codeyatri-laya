import { useEffect, useMemo, useRef, useState } from "react";
import { Sparkline } from "../components/Sparkline";
import { fmtMs, isNum, mean, percentile } from "../lib/derive";
import { useRecords } from "../lib/hooks";
import { backToLive, enterHistory, useStore } from "../lib/store";
import type { TimingStat } from "../lib/types";

type Key = "decide_ms" | "laya_ms" | "api_ms" | "turn_ms";

const SERIES: { key: Key; label: string; what: string; tone: "ember" | "cyan" | "ivory" | "acid" }[] = [
  { key: "decide_ms", label: "Decide", what: "facts, one Laya call and the pick (submission log timing.decide_ms)", tone: "ember" },
  { key: "laya_ms", label: "Laya call", what: "the Laya forward pass alone (decision event laya_ms)", tone: "acid" },
  { key: "api_ms", label: "Game API", what: "sending the move and reading the response (timing.api_ms)", tone: "cyan" },
  { key: "turn_ms", label: "Turn", what: "previous game response to this one (timing.turn_ms)", tone: "ivory" },
];

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setW(Math.max(200, Math.round(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, w };
}

function maxOf(v: (number | null)[]): number | null {
  let m: number | null = null;
  for (const x of v) if (x !== null && (m === null || x > m)) m = x;
  return m;
}

export function TimingView() {
  const records = useRecords();
  const summary = useStore((s) => s.feed?.meta?.summary);
  const envKind = useStore((s) => s.feed?.meta?.summary?.env_kind);
  const selection = useStore((s) => s.selection);
  const [hover, setHover] = useState<number | null>(null);
  const { ref, w } = useWidth();
  const sel = selection.mode === "history" ? selection.i : null;
  const sim = envKind === "simulator";

  const values = useMemo(() => {
    const out: Record<Key, (number | null)[]> = { decide_ms: [], laya_ms: [], api_ms: [], turn_ms: [] };
    for (const r of records) {
      out.decide_ms.push(isNum(r.timing?.decide_ms) ? r.timing!.decide_ms! : null);
      out.api_ms.push(isNum(r.timing?.api_ms) ? r.timing!.api_ms! : null);
      out.turn_ms.push(isNum(r.timing?.turn_ms) ? r.timing!.turn_ms! : null);
      out.laya_ms.push(isNum(r.event?.laya_ms) ? (r.event!.laya_ms as number) : null);
    }
    return out;
  }, [records]);

  const stats = useMemo(() => {
    const out = {} as Record<Key, TimingStat>;
    for (const s of SERIES) {
      const server = s.key !== "laya_ms" ? summary?.timing?.[s.key] : undefined;
      if (server) out[s.key] = server;
      else {
        const v = values[s.key].filter((x): x is number => x !== null);
        out[s.key] = { last: v.length ? v[v.length - 1] : null, mean: mean(v), p95: percentile(v, 0.95), n: v.length };
      }
    }
    return out;
  }, [summary, values]);

  const focus = hover ?? sel;
  const focusRec = focus !== null ? records[focus] : null;

  return (
    <div className="view timing-view">
      <header className="view-head">
        <div>
          <h1>Timing</h1>
          <p className="sub">Per-line values as logged. Each chart runs from 0 at the bottom to its max at the top. Point at a chart to read a line, click to inspect it across the dashboard.</p>
        </div>
        {sel !== null ? (
          <button type="button" className="btn-live" onClick={backToLive}>
            Back to live
          </button>
        ) : null}
      </header>
      <div className="readout panel mono" aria-live="off">
        {focusRec ? (
          <>
            <span>line {focusRec.i + 1}</span>
            <span>step {focusRec.step}</span>
            <span>{focusRec.result}</span>
            {SERIES.map((s) => (
              <span key={s.key}>
                {s.label} {s.key === "api_ms" && sim ? "local simulator" : fmtMs(values[s.key][focusRec.i])}
              </span>
            ))}
          </>
        ) : (
          <span className="muted">{records.length ? `${records.length} lines. Point at a chart to read one.` : "No lines logged yet."}</span>
        )}
      </div>
      <div ref={ref} className="timing-list">
        {SERIES.map((s) => {
          const st = stats[s.key];
          const simApi = s.key === "api_ms" && sim;
          return (
            <section key={s.key} className={`panel timing-row tone-${s.tone}`} aria-label={`${s.label} timing`}>
              <header>
                <div>
                  <h2>{s.label}</h2>
                  <p className="sub">{s.what}</p>
                </div>
                <dl className="tstats">
                  <div>
                    <dt>last</dt>
                    <dd className="mono">{simApi ? "sim" : fmtMs(st.last)}</dd>
                  </div>
                  <div>
                    <dt>mean</dt>
                    <dd className="mono">{simApi ? "sim" : fmtMs(st.mean)}</dd>
                  </div>
                  <div>
                    <dt>p95</dt>
                    <dd className="mono">{simApi ? "sim" : fmtMs(st.p95)}</dd>
                  </div>
                  <div>
                    <dt>max</dt>
                    <dd className="mono">{simApi ? "sim" : fmtMs(maxOf(values[s.key]))}</dd>
                  </div>
                  <div>
                    <dt>lines</dt>
                    <dd className="mono">{st.n}</dd>
                  </div>
                </dl>
              </header>
              {simApi ? (
                <p className="sim-note">Local simulator: there is no network call, so the log records api_ms as 0 for every line. It is not shown as a latency.</p>
              ) : st.n ? (
                <Sparkline
                  values={values[s.key]}
                  width={Math.max(200, w - 34)}
                  height={84}
                  selected={sel}
                  hover={hover}
                  onHover={setHover}
                  onSelect={(i) => enterHistory(i)}
                  tone={s.tone}
                  label={`${s.label} per line, ${st.n} values, mean ${fmtMs(st.mean)}, p95 ${fmtMs(st.p95)}`}
                />
              ) : (
                <p className="muted">Not logged for this session.</p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

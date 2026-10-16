import { motion } from "motion/react";
import { DIR_LABEL, fmtPct } from "../lib/derive";
import type { DirView } from "../lib/derive";
import { DUR, EASE } from "../lib/motion";

// Ring for Laya's raw yes-probability on one direction. Animates once per new decision (animKey).
export function YesGauge({ p, chosen, animKey, size = 58 }: { p: number; chosen: boolean; animKey: string; size?: number }) {
  const r = 23;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, p));
  return (
    <svg className={`gauge${chosen ? " is-chosen" : ""}`} width={size} height={size} viewBox="0 0 58 58" aria-hidden="true" focusable="false">
      <circle cx="29" cy="29" r={r} className="gauge-track" />
      {[0.25, 0.5, 0.75].map((t) => {
        const a = -Math.PI / 2 + t * 2 * Math.PI;
        return <line key={t} x1={29 + Math.cos(a) * 18.5} y1={29 + Math.sin(a) * 18.5} x2={29 + Math.cos(a) * 20.5} y2={29 + Math.sin(a) * 20.5} className="gauge-tick" />;
      })}
      <motion.circle
        key={animKey}
        cx="29"
        cy="29"
        r={r}
        className="gauge-arc"
        transform="rotate(-90 29 29)"
        strokeDasharray={c}
        initial={{ strokeDashoffset: c }}
        animate={{ strokeDashoffset: c * (1 - v) }}
        transition={{ duration: DUR.slow, ease: EASE.out }}
      />
    </svg>
  );
}

export function NotAskedRing({ size = 58 }: { size?: number }) {
  return (
    <svg className="gauge not-asked" width={size} height={size} viewBox="0 0 58 58" aria-hidden="true" focusable="false">
      <circle cx="29" cy="29" r="23" className="gauge-track dashed" />
      <path d="M14 44 L44 14" className="gauge-slash" />
    </svg>
  );
}

// One bar split across the asked directions by their normalised share (the logged probabilities block)
export function ShareBar({ dirs, animKey }: { dirs: DirView[]; animKey: string }) {
  const asked = dirs.filter((d) => d.asked && d.share !== null);
  const total = asked.reduce((a, d) => a + (d.share ?? 0), 0);
  if (!asked.length || total <= 0) return null;
  let x = 0;
  return (
    <figure className="share" aria-label="Share across asked moves, the normalised probabilities written to the log">
      <figcaption>
        <span className="label">Share across asked moves</span>
        <span className="hint">normalised from the yes-probabilities, sums to 100%</span>
      </figcaption>
      <svg className="share-bar" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        {asked.map((d) => {
          const w = ((d.share ?? 0) / total) * 100;
          const seg = (
            <motion.rect
              key={`${animKey}-${d.dir}`}
              x={x + 0.3}
              y={0}
              height={10}
              rx={1.2}
              className={`share-seg${d.chosen ? " is-chosen" : ""}`}
              initial={{ width: 0 }}
              animate={{ width: Math.max(0, w - 0.6) }}
              transition={{ duration: DUR.slow, ease: EASE.out }}
            />
          );
          x += w;
          return seg;
        })}
      </svg>
      <ul className="share-legend">
        {asked.map((d) => (
          <li key={d.dir} className={d.chosen ? "is-chosen" : undefined}>
            <span className="mono">{DIR_LABEL[d.dir]}</span> <span className="mono">{fmtPct(d.share)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

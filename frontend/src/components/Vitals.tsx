import { fmtInt, fmtPct, isNum, points2048 } from "../lib/derive";
import { useStore } from "../lib/store";
import type { Summary, VerifyResult } from "../lib/types";
import { ShieldGlyph } from "./Glyphs";

const SNAKE_WIN_FOODS = 15; // arena rule: "Eat 15 foods"
const LADDER = [64, 128, 256, 512, 1024, 2048];

export function StageGate({ game, summary }: { game: string | null | undefined; summary: Summary | null | undefined }) {
  if (!summary) return null;
  if (game === "snake") {
    const foods = summary.foods ?? 0;
    const target = summary.target_foods ?? 10;
    const pct = Math.min(1, foods / SNAKE_WIN_FOODS);
    return (
      <figure className="gate" aria-label={`Stage gate: ${foods} of ${target} foods needed for ${summary.target_points ?? 600} points`}>
        <figcaption>
          <span className="label">Stage gate</span>
          <span className={`gate-state${summary.unlocked ? " is-open" : ""}`}>{summary.unlocked ? "600 points reached" : `${Math.max(0, target - foods)} more foods to 600`}</span>
        </figcaption>
        <div className="gate-track">
          <div className="gate-fill" style={{ width: `${pct * 100}%` }} />
          <span className="gate-tick" style={{ left: `${(target / SNAKE_WIN_FOODS) * 100}%` }} title="600 points, 10 foods" />
        </div>
        <div className="gate-scale mono">
          <span>0</span>
          <span style={{ left: `${(target / SNAKE_WIN_FOODS) * 100}%` }}>10 = 600 pts</span>
        </div>
        <p className="gate-now mono" title="15 foods win the game for 1000 points">
          {foods} of 15 foods, length {fmtInt(summary.length)}
        </p>
      </figure>
    );
  }
  if (game === "2048") {
    const best = summary.best_tile ?? 0;
    const score = summary.score ?? 0;
    const pts = points2048(best, score);
    const tilePart = best > 0 ? Math.max(0, Math.floor(Math.log2(best)) - 6) : 0;
    return (
      <figure className="gate" aria-label={`Stage gate: best tile ${best}, target 512`}>
        <figcaption>
          <span className="label">Stage gate</span>
          <span className={`gate-state${summary.unlocked ? " is-open" : ""}`}>{summary.unlocked ? "512 tile reached" : "needs a 512 tile"}</span>
        </figcaption>
        <ol className="ladder">
          {LADDER.map((t) => (
            <li key={t} className={`${best >= t ? "is-reached" : ""}${t === 512 ? " is-gate" : ""}${best === t ? " is-best" : ""}`}>
              <span className="mono">{t}</span>
            </li>
          ))}
        </ol>
        <p className="gate-now mono" title="points = min(1000, max(0, log2(best tile) - 6) x 143 + floor(score / 1000))">
          max(0, log2({best || 0}) - 6) x 143 + floor({fmtInt(score)} / 1000) = {tilePart * 143} + {Math.floor(score / 1000)} = {pts}
        </p>
      </figure>
    );
  }
  return (
    <figure className="gate">
      <figcaption>
        <span className="label">Stage gate</span>
        <span className="gate-state">not defined for this game</span>
      </figcaption>
      <p className="gate-now muted">Points come from the session_end event or the final response when the game reports them.</p>
    </figure>
  );
}

export function VerifyChip({ verify, busy, error }: { verify: VerifyResult | null; busy: boolean; error: string | null }) {
  if (error) return <span className="chip chip-warn">Verify failed: {error}</span>;
  if (!verify) return <span className="chip chip-muted">{busy ? "Checking hash chain" : "Not checked yet"}</span>;
  if (verify.pending) return <span className="chip chip-muted">No complete line to check yet</span>;
  if (verify.ok)
    return (
      <span className="chip chip-ok">
        <ShieldGlyph size={14} state="ok" /> Log verified
      </span>
    );
  return (
    <span className="chip chip-bad">
      <ShieldGlyph size={14} state="bad" /> {verify.chain_ok === false ? "Hash chain broken" : `${verify.problems.length} rule problem${verify.problems.length === 1 ? "" : "s"}`}
    </span>
  );
}

export function FallbackMeter({ share, fallbacks, applied }: { share: number | null | undefined; fallbacks: number | undefined; applied: number | undefined }) {
  const v = isNum(share) ? share : 0;
  const over = v > 0.1;
  const scaleMax = Math.max(0.2, v * 1.15);
  return (
    <div className={`meter${over ? " is-over" : ""}`} aria-label={`Fallback share ${fmtPct(v)} of applied moves, limit 10%`}>
      <div className="meter-head">
        <span className="label">Fallback share</span>
        <span className="mono">
          {fmtPct(v)} <span className="muted">
            ({fmtInt(fallbacks ?? 0)} of {fmtInt(applied ?? 0)})
          </span>
        </span>
      </div>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${(v / scaleMax) * 100}%` }} />
        <span className="meter-limit" style={{ left: `${(0.1 / scaleMax) * 100}%` }} />
      </div>
      <div className="meter-scale mono">
        <span>0%</span>
        <span style={{ left: `${(0.1 / scaleMax) * 100}%` }}>10% limit</span>
      </div>
    </div>
  );
}

export function Vitals() {
  const meta = useStore((s) => s.feed?.meta ?? null);
  const summary = meta?.summary;
  const game = meta?.game;
  return (
    <section className="vitals" aria-label="Session vitals">
      <div className="vital-points">
        <span className="label">Points</span>
        <span className="big mono">{fmtInt(summary?.points)}</span>
        <span className="hint">{summary?.points_source === "session_end" ? "reported in session_end" : "computed from the latest state"}</span>
      </div>
      <dl className="vital-counts">
        <div>
          <dt>Applied</dt>
          <dd className="mono">{fmtInt(summary?.steps)}</dd>
        </div>
        <div>
          <dt>Rejected</dt>
          <dd className="mono">{fmtInt(summary?.rejected)}</dd>
        </div>
        <div>
          <dt>Decisions</dt>
          <dd className="mono">{fmtInt(summary?.decisions)}</dd>
        </div>
      </dl>
      <FallbackMeter share={summary?.fallback_share} fallbacks={summary?.fallbacks} applied={summary?.steps} />
      <StageGate game={game} summary={summary} />
    </section>
  );
}

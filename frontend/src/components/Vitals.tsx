import type { MouseEvent } from "react";
import { fmtInt, fmtPct, gameLabel, isNum, points2048 } from "../lib/derive";
import { fmtClock, useLeaderboard } from "../lib/leaderboard";
import { navigate } from "../lib/route";
import { useStore } from "../lib/store";
import type { Summary, VerifyResult } from "../lib/types";
import { ShieldGlyph } from "./Glyphs";

const SNAKE_WIN_FOODS = 15; // arena rule: "Eat 15 foods"
const LADDER = [64, 128, 256, 512, 1024, 2048];

// Progress toward the stage gate, as one short phrase plus a hairline bar
function gateParts(game: string | null | undefined, summary: Summary): { text: string; frac: number | null; tick: number | null; open: boolean } {
  if (game === "snake") {
    const foods = summary.foods ?? 0;
    const target = summary.target_foods ?? 10;
    return {
      text: `${foods} of ${SNAKE_WIN_FOODS} foods, ${summary.unlocked ? "600-point gate passed" : `${Math.max(0, target - foods)} more to the 600-point gate`}`,
      frac: Math.min(1, foods / SNAKE_WIN_FOODS),
      tick: target / SNAKE_WIN_FOODS,
      open: !!summary.unlocked,
    };
  }
  if (game === "2048") {
    const best = summary.best_tile ?? 0;
    const steps = best > 0 ? Math.max(0, Math.log2(best) - 5) : 0;
    return {
      text: `best tile ${fmtInt(best)}, ${summary.unlocked ? "512 gate passed" : "the gate is a 512 tile"}`,
      frac: Math.min(1, steps / (LADDER.length)),
      tick: 4 / LADDER.length,
      open: !!summary.unlocked,
    };
  }
  return { text: "no stage gate defined for this game", frac: null, tick: null, open: false };
}

// "#6 on the public Snake board": proof that this arena run is on the real leaderboard
function RankLine({ game, sessionId }: { game: string; sessionId: string }) {
  const { data } = useLeaderboard(game);
  const row = data?.leaderboard.find((r) => r.gameId === sessionId);
  if (!data || !row) return null;
  const go = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    navigate("leaderboard");
  };
  return (
    <a className="stat-rank" href="#/leaderboard" onClick={go}>
      <span className="stat-text is-open">
        #{row.rank} on the public {gameLabel(game)} board
      </span>
      <span className="stat-text">{data.stale ? `offline copy from ${fmtClock(data.fetched_at)}` : `fetched ${fmtClock(data.fetched_at)}`}</span>
    </a>
  );
}

function scenarioName(scenario: string | null | undefined): string {
  if (!scenario) return "Doom";
  const [wad, map] = scenario.split(":");
  if (map) return `${wad === "freedoom2" ? "Freedoom: Phase 2" : "Freedoom"} ${map}`;
  return scenario.replace(/_/g, " ");
}

export function doomOutcome(summary: Summary, done: boolean): string {
  if (!done) return `health ${fmtInt(summary.health ?? 0)}, playing`;
  return summary.exited ? "reached the level exit" : summary.dead ? "died" : "time limit reached";
}

function DoomStats({ summary, done }: { summary: Summary; done: boolean }) {
  const share = isNum(summary.fallback_share) ? summary.fallback_share : 0;
  return (
    <section className="stats" aria-label="Session numbers">
      <div className="stat-points">
        <span className="big num">{fmtInt(summary.kills ?? 0)}</span>
        <span className="stat-label">kills</span>
      </div>
      <div className="stat-gate">
        <span className={`stat-text${summary.exited ? " is-open" : ""}`}>
          {scenarioName(summary.scenario)}, {doomOutcome(summary, done)}
        </span>
        <span className="stat-text">{isNum(summary.explored) ? `${fmtInt(summary.explored)} areas explored` : "every action decided by Laya"}</span>
      </div>
      <div className="stat-moves">
        <span className="stat-text num">{fmtInt(summary.steps)} actions, held 4 game tics each</span>
        <span className={`stat-text num${share > 0.1 ? " is-warn" : ""}`}>fallback {fmtPct(share)} of a 10% limit</span>
      </div>
    </section>
  );
}

export function StatsLine() {
  const meta = useStore((s) => s.feed?.meta ?? null);
  const summary = meta?.summary;
  if (!summary) return <div className="stats" aria-hidden="true" />;
  if (meta?.game === "doom") return <DoomStats summary={summary} done={meta.status === "finished"} />;
  const arena = summary.source === "arena" && summary.env_kind === "hosted";
  const gate = gateParts(meta?.game, summary);
  const share = isNum(summary.fallback_share) ? summary.fallback_share : 0;
  return (
    <section className="stats" aria-label="Session numbers">
      <div className="stat-points">
        <span className="big num">{fmtInt(summary.points)}</span>
        <span className="stat-label">{summary.points_source === "session_end" ? "points" : "points so far"}</span>
      </div>
      <div className="stat-gate">
        <span className={`stat-text${gate.open ? " is-open" : ""}`}>{gate.text}</span>
        {gate.frac !== null ? (
          <span className="hair" aria-hidden="true">
            <span className="hair-fill" style={{ width: `${gate.frac * 100}%` }} />
            {gate.tick !== null ? <span className="hair-tick" style={{ left: `${gate.tick * 100}%` }} /> : null}
          </span>
        ) : null}
      </div>
      <div className="stat-moves">
        <span className="stat-text num">
          {fmtInt(summary.steps)} moves, {fmtInt(summary.rejected)} rejected
        </span>
        <span className={`stat-text num${share > 0.1 ? " is-warn" : ""}`} title={`${fmtInt(summary.fallbacks)} fallback moves of ${fmtInt(summary.steps)} applied; the rules allow up to 10%`}>
          fallback {fmtPct(share)} of a 10% limit
        </span>
      </div>
      {arena && meta?.game ? <RankLine game={meta.game} sessionId={meta.session_id} /> : null}
    </section>
  );
}

// Full stage-gate breakdown for the audit view
export function StageGate({ game, summary }: { game: string | null | undefined; summary: Summary | null | undefined }) {
  if (!summary) return null;
  if (game === "doom") {
    return (
      <figure className="gate">
        <figcaption>Stage 3: the real Doom</figcaption>
        <p className="gate-now">
          No unlock gate: the episode is judged on how the agent plays. {scenarioName(summary.scenario)}: {fmtInt(summary.kills ?? 0)} kills,{" "}
          {doomOutcome(summary, summary.done)}.
        </p>
      </figure>
    );
  }
  if (game === "2048") {
    const best = summary.best_tile ?? 0;
    const score = summary.score ?? 0;
    const tilePart = best > 0 ? Math.max(0, Math.floor(Math.log2(best)) - 6) : 0;
    return (
      <figure className="gate">
        <figcaption>Stage gate: a 512 tile</figcaption>
        <ol className="ladder">
          {LADDER.map((t) => (
            <li key={t} className={`${best >= t ? "is-reached" : ""}${t === 512 ? " is-gate" : ""}`}>
              <span className="num">{t}</span>
            </li>
          ))}
        </ol>
        <p className="gate-now num">
          max(0, log2({best || 0}) - 6) x 143 + floor({fmtInt(score)} / 1000) = {tilePart * 143} + {Math.floor(score / 1000)} = {points2048(best, score)} points
        </p>
      </figure>
    );
  }
  const parts = gateParts(game, summary);
  return (
    <figure className="gate">
      <figcaption>Stage gate</figcaption>
      <p className={`gate-now${parts.open ? " is-open" : ""}`}>{parts.text}</p>
      {parts.frac !== null ? (
        <span className="hair" aria-hidden="true">
          <span className="hair-fill" style={{ width: `${parts.frac * 100}%` }} />
          {parts.tick !== null ? <span className="hair-tick" style={{ left: `${parts.tick * 100}%` }} /> : null}
        </span>
      ) : null}
    </figure>
  );
}

export function VerifyChip({ verify, busy, error }: { verify: VerifyResult | null; busy: boolean; error: string | null }) {
  if (error) return <span className="verify is-warn">Check failed</span>;
  if (!verify) return <span className="verify is-wait">{busy ? "Checking" : "Not checked"}</span>;
  if (verify.pending) return <span className="verify is-wait">No line yet</span>;
  if (verify.ok)
    return (
      <span className="verify is-ok" title="Hash chain, step order, decision blocks and fallback share checked by /api/verify">
        <ShieldGlyph size={14} state="ok" /> Verified
      </span>
    );
  return (
    <span className="verify is-bad" title={verify.problems.slice(0, 3).join("; ")}>
      <ShieldGlyph size={14} state="bad" /> {verify.chain_ok === false ? "Chain broken" : `${verify.problems.length} problem${verify.problems.length === 1 ? "" : "s"}`}
    </span>
  );
}

export function FallbackMeter({ share, fallbacks, applied }: { share: number | null | undefined; fallbacks: number | undefined; applied: number | undefined }) {
  const v = isNum(share) ? share : 0;
  const scaleMax = Math.max(0.2, v * 1.15);
  return (
    <div className={`meter${v > 0.1 ? " is-over" : ""}`}>
      <p>
        Fallback share <span className="num">{fmtPct(v)}</span>{" "}
        <span className="muted num">
          ({fmtInt(fallbacks ?? 0)} of {fmtInt(applied ?? 0)}, limit 10%)
        </span>
      </p>
      <span className="hair" aria-hidden="true">
        <span className="hair-fill" style={{ width: `${(v / scaleMax) * 100}%` }} />
        <span className="hair-tick is-limit" style={{ left: `${(0.1 / scaleMax) * 100}%` }} />
      </span>
    </div>
  );
}

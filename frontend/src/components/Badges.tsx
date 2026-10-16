import { envLabel, statusText } from "../lib/derive";
import type { DecisionView } from "../lib/derive";
import type { EnvKind, Status, Summary } from "../lib/types";
import { FallbackGlyph, GlobeGlyph, SimGlyph } from "./Glyphs";

export function EnvBadge({ kind, env }: { kind: EnvKind | undefined; env?: string | null }) {
  const k = kind ?? "unknown";
  const title =
    k === "hosted"
      ? `Real arena session (env ${env ?? "HOSTED"})`
      : k === "simulator"
        ? `Local simulator session (env ${env ?? "not logged"}): a test run, never an arena result`
        : k === "engine"
          ? "Our own copy of the Doom engine (ViZDoom with Freedoom data); stage 3 is not played on the hosted arena"
          : "The session_start event has no env label";
  return (
    <span className={`env-badge env-${k}`} title={title}>
      {k === "hosted" ? <GlobeGlyph size={13} /> : <SimGlyph size={13} />}
      <span>{k === "hosted" ? "Hosted arena" : k === "simulator" ? "Simulator run" : envLabel(k)}</span>
    </span>
  );
}

export function StatusBadge({ status, summary, ageS }: { status: Status | undefined | null; summary?: Summary | null; ageS?: number | null }) {
  const t = statusText(status, summary, ageS);
  return (
    <span className={`status status-${status ?? "loading"}`} title={t.detail}>
      <span className="status-dot" aria-hidden="true" />
      <span>{t.label}</span>
    </span>
  );
}

// One quiet line instead of a row of pills: who decided, and what happened to the move
export function DecisionLine({ decision }: { decision: DecisionView }) {
  const fallback = decision.source === "fallback";
  const who = fallback ? "Fallback move" : decision.source === "laya" ? "Laya decided" : "Source not logged";
  const what =
    decision.result === "applied"
      ? "applied"
      : decision.result === "rejected"
        ? "rejected by the game"
        : decision.result === "awaiting"
          ? "waiting for the game"
          : decision.result === "unsent"
            ? "never sent, the session ended"
            : String(decision.result);
  return (
    <p className={`decision-line${fallback ? " is-fallback" : ""}${decision.result === "rejected" ? " is-rejected" : ""}`}>
      {fallback ? <FallbackGlyph size={14} /> : null}
      <span>
        {who}, {what}
      </span>
    </p>
  );
}

import { envLabel, statusText } from "../lib/derive";
import type { EnvKind, Status, Summary } from "../lib/types";
import { AppliedGlyph, FallbackGlyph, GlobeGlyph, PendingGlyph, RejectedGlyph, SimGlyph } from "./Glyphs";

export function EnvBadge({ kind, env, compact = false }: { kind: EnvKind | undefined; env?: string | null; compact?: boolean }) {
  const k = kind ?? "unknown";
  const title =
    k === "hosted"
      ? `Real arena session (env ${env ?? "HOSTED"})`
      : k === "simulator"
        ? `Local simulator session (env ${env ?? "not logged"}): a test run, never an arena result`
        : "The session_start event has no env label";
  return (
    <span className={`badge env env-${k}`} title={title}>
      {k === "hosted" ? <GlobeGlyph size={13} /> : <SimGlyph size={13} />}
      <span>{compact ? (k === "hosted" ? "HOSTED" : k === "simulator" ? "SIM" : "ENV ?") : envLabel(k).toUpperCase()}</span>
    </span>
  );
}

export function StatusBadge({ status, summary, ageS }: { status: Status | undefined | null; summary?: Summary | null; ageS?: number | null }) {
  const t = statusText(status, summary, ageS);
  return (
    <span className={`badge status status-${status ?? "loading"}`} title={t.detail}>
      <span className="status-dot" aria-hidden="true" />
      <span>{t.label}</span>
    </span>
  );
}

export function SourceBadge({ source, large = false }: { source: string | null | undefined; large?: boolean }) {
  if (source === "fallback")
    return (
      <span className={`badge source source-fallback${large ? " large" : ""}`} title="A rule-based safety move, not Laya's pick">
        <FallbackGlyph size={large ? 16 : 13} />
        <span>FALLBACK</span>
      </span>
    );
  if (source === "laya")
    return (
      <span className={`badge source source-laya${large ? " large" : ""}`} title="The move is Laya's highest yes-probability">
        <span className="laya-dot" aria-hidden="true" />
        <span>LAYA</span>
      </span>
    );
  return <span className="badge source source-unknown">SOURCE n/a</span>;
}

export function ResultBadge({ result }: { result: string | null | undefined }) {
  switch (result) {
    case "applied":
      return (
        <span className="badge result result-applied">
          <AppliedGlyph size={13} />
          <span>APPLIED</span>
        </span>
      );
    case "rejected":
      return (
        <span className="badge result result-rejected">
          <RejectedGlyph size={13} />
          <span>REJECTED</span>
        </span>
      );
    case "awaiting":
      return (
        <span className="badge result result-awaiting" title="Decision logged, move sent or about to be sent, no game response logged yet">
          <PendingGlyph size={13} />
          <span>AWAITING GAME</span>
        </span>
      );
    case "unsent":
      return (
        <span className="badge result result-unsent" title="The session ended before this decision became a logged move">
          <PendingGlyph size={13} />
          <span>NOT SENT</span>
        </span>
      );
    default:
      return <span className="badge result">{String(result ?? "n/a").toUpperCase()}</span>;
  }
}

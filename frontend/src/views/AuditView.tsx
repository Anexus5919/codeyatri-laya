import { EnvBadge, StatusBadge } from "../components/Badges";
import { ShieldGlyph } from "../components/Glyphs";
import { FallbackMeter, StageGate } from "../components/Vitals";
import { recheckVerify, replayVerify } from "../lib/feed";
import { fmtAge, fmtInt, fmtTs, gameLabel } from "../lib/derive";
import { useRecords } from "../lib/hooks";
import { enterHistory, useStore } from "../lib/store";

function Field({ k, v, mono = true }: { k: string; v: unknown; mono?: boolean }) {
  const text = v === null || v === undefined || v === "" ? "not logged" : typeof v === "object" ? JSON.stringify(v) : String(v);
  return (
    <div className="field">
      <dt>{k}</dt>
      <dd className={mono ? "num" : undefined}>{text}</dd>
    </div>
  );
}

export function AuditView() {
  const meta = useStore((s) => s.feed?.meta ?? null);
  const verify = useStore((s) => s.verify);
  const busy = useStore((s) => s.verifyBusy);
  const vErr = useStore((s) => s.verifyError);
  const verifyAt = useStore((s) => s.verifyAt);
  const records = useRecords();
  const summary = meta?.summary;
  const start = meta?.session_start;
  const load = (start?.load ?? {}) as Record<string, unknown>;
  const end = meta?.session_end;
  const final = meta?.final;
  const tail = records.slice(-8);
  const state = verify ? (verify.pending ? "wait" : verify.ok ? "ok" : "bad") : "wait";
  const doom = meta?.game === "doom";

  return (
    <div className="view audit-view">
      <header className="view-head">
        <div>
          <h1>Audit and verification</h1>
          <p className="sub">
            {doom
              ? "Checked by the server: hash chain, step order and decision blocks, plus the engine's demo recording of the episode, which replays exactly."
              : "Checked by the server with the same rules the submission is judged on: hash chain, step order, decision blocks, fallback share and the final response."}
          </p>
        </div>
        <button type="button" className="btn" onClick={recheckVerify} disabled={busy}>
          {busy ? "Checking..." : "Re-check now"}
        </button>
      </header>

      <div className="audit-grid">
        <section className={`panel verdict verdict-${state}`} aria-label="Verification result">
          <div className="verdict-main">
            <ShieldGlyph size={44} state={state} />
            <div>
              <h2>{!verify ? (vErr ? "Verification failed to run" : "Not checked yet") : verify.pending ? "No complete line yet" : verify.ok ? "Log verified" : "Problems found"}</h2>
              <p className="sub">
                {verifyAt ? `checked ${fmtAge((Date.now() - verifyAt) / 1000)}` : ""} {vErr ? `error: ${vErr}` : ""}
              </p>
            </div>
          </div>
          {verify && !verify.pending ? (
            <dl className="verdict-facts">
              <Field k="hash chain" v={verify.chain_ok === null ? "n/a" : verify.chain_ok ? "intact" : "broken"} />
              <Field k="lines" v={verify.lines} />
              <Field k="applied" v={verify.applied} />
              <Field k="fallbacks" v={verify.fallbacks} />
              {doom ? null : <Field k="final response" v={verify.final_done === undefined ? "not saved yet" : `done ${String(verify.final_done)}, score ${String(verify.final_score)}`} />}
            </dl>
          ) : null}
          {doom && verify && verify.checks ? (
            <>
              <ul className="verify-checks">
                {Object.entries(verify.checks).map(([k, ok]) => (
                  <li key={k} className={ok ? "is-ok" : "is-bad"}>
                    <span className="dot" aria-hidden="true" />
                    {k}: {ok ? "yes" : "no"}
                  </li>
                ))}
              </ul>
              <div className="replay-row">
                <button type="button" className="btn" onClick={() => void replayVerify()} disabled={busy || meta?.status !== "finished"}>
                  {busy ? "Replaying..." : "Replay the recording in the engine"}
                </button>
                <span className="small muted">
                  {verify.replay
                    ? `Engine replay: ${verify.replay.kills} kills, health ${verify.replay.health}, ${verify.replay.dead ? "died" : verify.replay.exited ? "level exit" : "time limit"} at tic ${verify.replay.tic}`
                    : meta?.status === "finished"
                      ? "Plays the demo back in the engine and compares kills and how the episode ended."
                      : "Available once the episode has ended."}
                </span>
              </div>
            </>
          ) : null}
          {verify && verify.problems.length ? (
            <ol className="problems">
              {verify.problems.slice(0, 40).map((p, k) => (
                <li key={k} className="raw">
                  {p}
                </li>
              ))}
              {verify.problems.length > 40 ? <li className="muted">and {verify.problems.length - 40} more</li> : null}
            </ol>
          ) : null}
        </section>

        <section className="panel" aria-label="Session identity">
          <header className="panel-head">
            <h2>Session</h2>
            <div className="badges">
              <EnvBadge kind={summary?.env_kind} env={summary?.env} />
              <StatusBadge status={meta?.status} summary={summary} ageS={meta?.age_s} />
            </div>
          </header>
          <dl className="fields">
            <Field k="session_id" v={meta?.session_id} />
            <Field k="game" v={gameLabel(meta?.game)} mono={false} />
            <Field k="agent_name" v={start?.agent_name} />
            <Field k="env" v={start?.env} />
            <Field k="model" v={start?.model} />
            <Field k="model_source" v={start?.model_source} />
            <Field k="device" v={start?.device ?? load.device} />
            <Field k="laya_version" v={load.laya_version} />
            <Field k="revision" v={load.revision} />
            <Field k="load_s" v={load.load_s} />
            <Field k="design" v={start?.design} />
            <Field k="offer" v={start?.offer} />
            <Field k="style" v={load.style} />
            <Field k="started" v={fmtTs(start?.ts)} />
            <Field k="ended" v={end?.ts ? fmtTs(end.ts) : null} />
            <Field k="folder" v={meta?.folder} />
          </dl>
        </section>

        <section className="panel" aria-label="Counts and limits">
          <header className="panel-head">
            <h2>Counts and limits</h2>
          </header>
          <dl className="fields">
            <Field k="log lines" v={summary?.lines} />
            <Field k={doom ? "applied actions" : "applied moves"} v={summary?.steps} />
            {doom ? null : <Field k="rejected moves" v={summary?.rejected} />}
            <Field k="decision events" v={summary?.decisions} />
            <Field k="unreadable log lines" v={meta?.bad_lines} />
          </dl>
          <FallbackMeter share={summary?.fallback_share} fallbacks={summary?.fallbacks} applied={summary?.steps} />
          <StageGate game={meta?.game} summary={summary} />
        </section>

        <section className="panel" aria-label="Outcome">
          <header className="panel-head">
            <h2>Outcome</h2>
          </header>
          {doom ? (
            <dl className="fields">
              <Field k="scenario" v={summary?.scenario} />
              <Field k="kills" v={summary?.kills} />
              <Field k="health" v={summary?.health} />
              <Field k="died" v={summary?.dead} />
              <Field k="level exit reached" v={summary?.exited} />
              <Field k="items picked up" v={summary?.items} />
              <Field k="areas explored" v={summary?.explored} />
              <Field k="recording" v={final ? (final as Record<string, unknown>).recording : null} />
              <Field k="recording sha256" v={final ? (final as Record<string, unknown>).recording_sha256 : null} />
            </dl>
          ) : (
            <dl className="fields">
              <Field k="points" v={summary?.points} />
              <Field k="points source" v={summary?.points_source === "session_end" ? "session_end event" : "computed from the latest state"} mono={false} />
              <Field k="points computed" v={summary?.points_computed} />
              <Field k="won" v={summary?.won} />
              <Field k="final response score" v={final?.score} />
              <Field k="final response steps" v={final?.steps} />
              <Field k="session_end" v={end ? `score ${String(end.score)}, steps ${String(end.steps)}, done ${String(end.done)}` : null} />
            </dl>
          )}
        </section>

        <section className="panel chain" aria-label="Hash chain tail">
          <header className="panel-head">
            <div>
              <h2>Chain tail</h2>
              <p className="sub">Each line's hash covers the previous hash, so editing any earlier line breaks every link after it. First 16 hex characters shown.</p>
            </div>
          </header>
          {tail.length ? (
            <ol className="links">
              {tail.map((r) => (
                <li key={r.i}>
                  <button type="button" className="link-node" onClick={() => enterHistory(r.i)} title="Inspect this line">
                    <span className="small muted">Line {fmtInt(r.i + 1)}</span>
                    <span className="mono">{r.hash}</span>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">No lines yet.</p>
          )}
        </section>
      </div>
    </div>
  );
}

import { selectSession } from "../lib/feed";
import { fmtInt, gameLabel, shortId } from "../lib/derive";
import { fmtClock, fmtWhen, OUR_AGENT, refreshLeaderboard, useLeaderboard, type LeaderboardData } from "../lib/leaderboard";
import { navigate } from "../lib/route";
import { useStore } from "../lib/store";

export function FetchState({ data, error, loading }: { data: LeaderboardData | null; error: string | null; loading: boolean }) {
  if (!data) return <span className="muted">{error ? `Viewer API unreachable: ${error}` : loading ? "Fetching the public board" : ""}</span>;
  if (data.stale && data.fetched_at) return <span className="lb-stale">Offline, showing the copy from {fmtClock(data.fetched_at)}</span>;
  if (data.stale) return <span className="lb-stale">Leaderboard unavailable ({data.error})</span>;
  return <span className="muted">Fetched {fmtClock(data.fetched_at)} from topgameai.com</span>;
}

export function LeaderboardView() {
  const game = useStore((s) => s.game) ?? "snake";
  const current = useStore((s) => s.sessionId);
  const { data, error, loading } = useLeaderboard(game);
  const rows = data?.leaderboard ?? [];
  const local = data?.local ?? {};
  const name = gameLabel(game === "unknown" ? null : game);
  const ours = rows.filter((r) => r.agentName === OUR_AGENT);

  const open = (key: string) => {
    selectSession(key, { manual: true });
    navigate("arena");
  };

  return (
    <div className="view leaderboard-view">
      <header className="view-head">
        <div>
          <h1>Public leaderboard, {name}</h1>
          <p className="sub">
            <FetchState data={data} error={error} loading={loading} />
            {ours.length ? `. ${OUR_AGENT} holds ${ours.map((r) => `#${r.rank}`).join(" and ")}.` : ""}
          </p>
        </div>
        <button type="button" className="btn" onClick={() => refreshLeaderboard(game)} disabled={loading}>
          {loading ? "Fetching" : "Refresh"}
        </button>
      </header>
      {rows.length ? (
        <div className="panel lb-panel">
          <table className="lb-table">
            <thead>
              <tr>
                <th scope="col" className="lb-rank">Rank</th>
                <th scope="col">Agent</th>
                <th scope="col" className="lb-num">Points</th>
                <th scope="col" className="lb-num">Steps</th>
                <th scope="col">Session</th>
                <th scope="col">Played</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, k) => {
                const key = r.gameId ? local[r.gameId] : undefined;
                const mine = r.agentName === OUR_AGENT;
                return (
                  <tr key={`${r.rank}-${r.gameId}-${k}`} className={`${mine ? "is-ours" : ""}${key && key === current ? " is-current" : ""}`}>
                    <td className="lb-rank num">{r.rank ?? "n/a"}</td>
                    <td className="lb-agent">{r.agentName ?? "n/a"}</td>
                    <td className="lb-num num">{fmtInt(r.score)}</td>
                    <td className="lb-num num">{fmtInt(r.steps)}</td>
                    <td>
                      {key ? (
                        <button type="button" className="lb-link mono" onClick={() => open(key)} title="Open this session from the local logs">
                          {shortId(r.gameId)}
                        </button>
                      ) : (
                        <span className="mono muted" title={mine ? "Not in the local runs folders" : undefined}>
                          {shortId(r.gameId)}
                        </span>
                      )}
                    </td>
                    <td className="muted num">{fmtWhen(r.timestamp)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="lb-foot muted small">Rows exactly as the arena returns them. A session id that matches a local log opens it.</p>
        </div>
      ) : (
        <p className="muted">{data && !data.stale ? `The public board for ${name} is empty.` : ""}</p>
      )}
    </div>
  );
}

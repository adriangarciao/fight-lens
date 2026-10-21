import { Link } from "react-router-dom";
import { api, type TrackMetrics } from "../api";
import { fmtDate, METHOD_LABEL } from "../format";
import { useAsync } from "../useAsync";

const pct = (x: number | null) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const num = (x: number | null) => (x == null ? "—" : x.toFixed(3));

function Tiles({ m }: { m: TrackMetrics }) {
  const vsCoin = m.log_loss == null ? null : m.coin_flip_log_loss - m.log_loss;
  return (
    <div className="tiles">
      <div className="tile">
        <span className="tile-value">{m.n}</span>
        <span className="kicker">Fights scored</span>
      </div>
      <div className="tile">
        <span className="tile-value">{pct(m.accuracy)}</span>
        <span className="kicker">Favourite won</span>
      </div>
      <div className="tile">
        <span className="tile-value">{num(m.log_loss)}</span>
        <span className="kicker">
          Log loss{vsCoin != null && ` (${vsCoin >= 0 ? "−" : "+"}${Math.abs(vsCoin).toFixed(3)} vs coin flip)`}
        </span>
      </div>
      <div className="tile">
        <span className="tile-value">{num(m.brier)}</span>
        <span className="kicker">Brier score</span>
      </div>
    </div>
  );
}

export function TrackRecordPage() {
  const { data, error, loading } = useAsync(api.trackRecord, []);
  if (loading) return <p className="loading">Loading track record</p>;
  if (error || !data) return <p className="error">{error ?? "Unavailable"}</p>;
  const h = data.headline;
  return (
    <>
      <div className="kicker">Live results</div>
      <h1>Track record</h1>
      <p className="small muted" style={{ maxWidth: 720 }}>
        Only predictions stored <strong>before fight day</strong> count, one per bout (the latest made before the fight).
        Draws and no-contests are void. Historical accuracy from backtests is a separate measure and is in the{" "}
        <a href="https://github.com/adriangarciao/fight-lens/blob/main/docs/model-report.md">model report</a>.
      </p>

      <Tiles m={h} />
      <p className="mono small muted">
        {data.pending} prediction(s) awaiting results
        {data.next_event && data.next_event_date && ` · next: ${data.next_event} (${fmtDate(data.next_event_date)})`}
        {data.voided > 0 && ` · ${data.voided} void`}
        {data.excluded_not_pre_fight > 0 && ` · ${data.excluded_not_pre_fight} excluded (not made before fight day)`}
      </p>

      {h.n === 0 ? (
        <p className="empty" style={{ fontSize: 18 }}>
          No results yet.
          {data.next_event
            ? ` The first scored fights arrive after ${data.next_event}.`
            : " Store predictions for an upcoming card with `fightlens predict`."}{" "}
          Small samples are noisy, so expect the numbers to swing until a few cards are in.
        </p>
      ) : (
        <>
          {h.n < 50 && (
            <div className="flag big-flag">
              Only {h.n} fights so far. Treat these numbers as anecdote, not evidence, until the sample grows.
            </div>
          )}
          <section className="section">
            <div className="section-head">
              <h2>Recent calls</h2>
            </div>
            <table className="results-table">
              <thead>
                <tr className="mono small muted">
                  <th>Date</th>
                  <th>Bout</th>
                  <th>Model said</th>
                  <th>Result</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.recent.map((r) => {
                  const fav = r.p_a >= 0.5 ? r.fighter_a : r.fighter_b;
                  const favP = Math.max(r.p_a, 1 - r.p_a);
                  return (
                    <tr key={r.bout_id}>
                      <td className="mono small">{fmtDate(r.event_date)}</td>
                      <td>
                        <Link to={`/compare?a=${r.fighter_a.id}&b=${r.fighter_b.id}&asOf=${r.event_date}`}>
                          {r.fighter_a.name} vs {r.fighter_b.name}
                        </Link>
                        <div className="small muted">{r.event_name}</div>
                      </td>
                      <td className="small">
                        {fav.name} {Math.round(favP * 100)}%
                      </td>
                      <td className="small">
                        {r.status === "void"
                          ? { draw: "Draw", no_contest: "No contest", pairing_changed: "Opponent changed" }[
                              r.actual_outcome
                            ] ?? r.actual_outcome
                          : `${r.winner?.name} by ${METHOD_LABEL[r.actual_method ?? ""] ?? r.actual_method}`}
                      </td>
                      <td className="mono">
                        {r.status === "void" ? (
                          <span className="muted">void</span>
                        ) : r.favourite_correct == null ? (
                          <span className="muted">50/50</span>
                        ) : r.favourite_correct ? (
                          <span className="hit">✓</span>
                        ) : (
                          <span className="miss">✗</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {data.calibration.length > 0 && (
            <section className="section">
              <div className="section-head">
                <h2>Calibration</h2>
                <span className="mono small muted">does a 70% favourite win about 70% of the time?</span>
              </div>
              <table className="tape">
                <tbody>
                  {data.calibration.map((c) => (
                    <tr key={c.bucket}>
                      <td>{c.bucket}</td>
                      <td className="label">{c.n} fights</td>
                      <td>
                        predicted {pct(c.mean_predicted)} · won {pct(c.observed)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {data.by_model_version.length > 1 && (
            <section className="section">
              <div className="section-head">
                <h2>By model version</h2>
              </div>
              <table className="tape">
                <tbody>
                  {data.by_model_version.map((v) => (
                    <tr key={v.model_version}>
                      <td>{v.model_version}</td>
                      <td className="label">{v.metrics.n} fights</td>
                      <td>
                        {pct(v.metrics.accuracy)} · log loss {num(v.metrics.log_loss)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </>
  );
}

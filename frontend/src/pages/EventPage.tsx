import { Link, useParams } from "react-router-dom";
import { api, type CardBout } from "../api";
import { SplitBar } from "../components/PredictionPanel";
import { fmtDate, fmtFinish, fmtRecord, method } from "../format";
import { useAsync } from "../useAsync";

function Bout({ b, date, i }: { b: CardBout; date: string; i: number }) {
  const done = b.status === "completed";
  return (
    <div className="bout" style={{ animationDelay: `${i * 35}ms` }}>
      <div className="side">
        <span className={`name ${b.winner_id === b.fighter_1.id ? "won" : ""}`}>{b.fighter_1.name}</span>
        <span className="mono small muted">{fmtRecord(b.record_1)} UFC</span>
      </div>
      <div className="meta">
        <span className="vs">VS</span>
        <span className="mono small">{b.division ?? b.weight_class_raw}</span>
        <span className="mono small muted">
          {b.scheduled_rounds ? `${b.scheduled_rounds} rds` : ""}
          {b.scheduled_rounds_source?.startsWith("rule:") ? " (inferred)" : ""}
          {b.is_title_bout ? " · title" : ""}
        </span>
        {done && (
          <span className="small">
            {b.outcome === "win" ? method(b.method, null) : b.outcome === "draw" ? "Draw" : "No contest"}
            <span className="muted"> {fmtFinish(b.end_round, b.end_time_seconds)}</span>
          </span>
        )}
        {b.prediction ? (
          <div className="card-pred">
            <div className="pcts">
              <span className="side-a">{Math.round(b.prediction.p_1 * 100)}%</span>
              <span className="side-b">{Math.round(b.prediction.p_2 * 100)}%</span>
            </div>
            <SplitBar a={b.prediction.p_1} b={b.prediction.p_2} compact />
            <div className="small muted" style={{ marginTop: 4 }}>
              Most likely: {b.prediction.likely_outcome} ({Math.round(b.prediction.likely_outcome_probability * 100)}%)
            </div>
          </div>
        ) : (
          !done && <span className="mono small muted">No stored prediction yet</span>
        )}
        <Link
          className="btn ghost"
          to={`/compare?a=${b.fighter_1.id}&b=${b.fighter_2.id}&asOf=${date}&rounds=${b.scheduled_rounds === 5 ? 5 : 3}${b.is_title_bout ? "&title=1" : ""}`}
        >
          Breakdown
        </Link>
      </div>
      <div className="side right">
        <span className={`name ${b.winner_id === b.fighter_2.id ? "won" : ""}`}>{b.fighter_2.name}</span>
        <span className="mono small muted">{fmtRecord(b.record_2)} UFC</span>
      </div>
    </div>
  );
}

export function EventPage() {
  const id = Number(useParams().id);
  const { data, error, loading } = useAsync(() => api.event(id), [id]);
  if (loading) return <p className="loading">Loading card</p>;
  if (error || !data) return <p className="error">{error ?? "Not found"}</p>;
  return (
    <>
      <div className="kicker">
        {fmtDate(data.date)} · {data.location} · <span>{data.status}</span>
      </div>
      <h1>{data.name}</h1>
      {data.bouts.some((b) => b.prediction) && (
        <p className="mono small muted">
          Model {data.bouts.find((b) => b.prediction)?.prediction?.model_version} · generated{" "}
          {new Date(data.bouts.find((b) => b.prediction)!.prediction!.generated_at).toLocaleString()} · model estimates,
          not betting odds
        </p>
      )}
      <p className="small muted">
        Records shown are UFC bouts in the source data before this event. The order fighters are listed in comes from the
        source and doesn't mean anything.
      </p>
      <div className="section">
        {data.bouts.map((b, i) => (
          <Bout key={b.bout_id} b={b} date={data.date} i={i} />
        ))}
      </div>
    </>
  );
}

import { Link, useParams } from "react-router-dom";
import { api, type CardBout } from "../api";
import { SplitBar } from "../components/PredictionPanel";
import { fmtDate, fmtFinish, fmtRecord, method } from "../format";
import { useAsync } from "../useAsync";

type Verdict = "hit" | "miss" | "void" | "toss";

function verdictOf(b: CardBout): Verdict | null {
  const r = b.prediction?.result;
  if (!r) return null;
  if (r.status === "void") return "void";
  if (r.favourite_correct == null) return "toss";
  return r.favourite_correct ? "hit" : "miss";
}

const VERDICT_LABEL: { [k in Verdict]: string } = {
  hit: "✓ Called it",
  miss: "✗ Missed",
  void: "Void · no winner",
  toss: "50/50 call",
};

function actualText(b: CardBout) {
  if (b.outcome === "win") {
    const w = b.winner_id === b.fighter_1.id ? b.fighter_1 : b.fighter_2;
    return `${w.name} by ${method(b.method, null)}`;
  }
  return b.outcome === "draw" ? "Draw" : "No contest";
}

function Bout({ b, date, i }: { b: CardBout; date: string; i: number }) {
  const done = b.status === "completed";
  const p = b.prediction;
  const pickId = p && p.p_1 !== p.p_2 ? (p.p_1 > p.p_2 ? b.fighter_1.id : b.fighter_2.id) : null;
  const pick = pickId === b.fighter_1.id ? b.fighter_1 : pickId === b.fighter_2.id ? b.fighter_2 : null;
  const verdict = verdictOf(b);

  const side = (f: CardBout["fighter_1"], rec: CardBout["record_1"], right: boolean) => (
    <div className={`side ${right ? "right" : ""}`}>
      <span className={`name ${done && b.winner_id === f.id ? "won" : ""}`}>{f.name}</span>
      <span className="mono small muted">{fmtRecord(rec)} UFC</span>
      {(pickId === f.id || (done && b.winner_id === f.id)) && (
        <span className="chips">
          {pickId === f.id && <span className="chip pick">{done ? "Predicted" : "Pick"}</span>}
          {done && b.winner_id === f.id && <span className="chip actual">Actual winner</span>}
        </span>
      )}
    </div>
  );

  return (
    <div className={`bout${verdict ? ` v-${verdict}` : ""}`} style={{ animationDelay: `${i * 35}ms` }}>
      {side(b.fighter_1, b.record_1, false)}
      <div className="meta">
        <span className="vs">VS</span>
        <span className="mono small">{b.division ?? b.weight_class_raw}</span>
        <span className="mono small muted">
          {b.scheduled_rounds ? `${b.scheduled_rounds} rds` : ""}
          {b.scheduled_rounds_source?.startsWith("rule:") ? " (inferred)" : ""}
          {b.is_title_bout ? " · title" : ""}
        </span>
        {p ? (
          <div className="card-pred">
            <div className="pcts">
              <span className="side-a">{Math.round(p.p_1 * 100)}%</span>
              <span className="side-b">{Math.round(p.p_2 * 100)}%</span>
            </div>
            <SplitBar a={p.p_1} b={p.p_2} compact />
            {done ? (
              <dl className="pva">
                <dt className="pva-label pick">Predicted</dt>
                <dd>
                  {pick ? `${pick.name} ${Math.round(Math.max(p.p_1, p.p_2) * 100)}%` : "Toss-up"}
                  <span className="muted">
                    {" "}
                    · likely {p.likely_outcome} ({Math.round(p.likely_outcome_probability * 100)}%)
                  </span>
                </dd>
                <dt className="pva-label actual">Actual</dt>
                <dd>
                  {actualText(b)}
                  <span className="muted"> {fmtFinish(b.end_round, b.end_time_seconds)}</span>
                </dd>
              </dl>
            ) : (
              <div className="small muted" style={{ marginTop: 4 }}>
                Most likely: {p.likely_outcome} ({Math.round(p.likely_outcome_probability * 100)}%)
              </div>
            )}
            {verdict && (
              <span className={`verdict ${verdict}`}>
                {VERDICT_LABEL[verdict]}
                {(verdict === "hit" || verdict === "miss") &&
                  ` · gave winner ${Math.round((p.result?.p_actual_winner ?? 0) * 100)}%`}
              </span>
            )}
          </div>
        ) : done ? (
          <>
            <span className="small">
              {actualText(b)}
              <span className="muted"> {fmtFinish(b.end_round, b.end_time_seconds)}</span>
            </span>
            <span className="mono small muted">No pre-fight prediction stored</span>
          </>
        ) : (
          <span className="mono small muted">No stored prediction yet</span>
        )}
        <Link
          className="btn ghost"
          to={`/compare?a=${b.fighter_1.id}&b=${b.fighter_2.id}&asOf=${date}&rounds=${b.scheduled_rounds === 5 ? 5 : 3}${b.is_title_bout ? "&title=1" : ""}`}
        >
          Breakdown
        </Link>
      </div>
      {side(b.fighter_2, b.record_2, true)}
    </div>
  );
}

function CardScore({ bouts }: { bouts: CardBout[] }) {
  const v = bouts.map(verdictOf).filter((x): x is Verdict => x != null);
  if (v.length === 0) return null;
  const hits = v.filter((x) => x === "hit").length;
  const decided = hits + v.filter((x) => x === "miss").length;
  return (
    <div className="card-score">
      <span className="kicker">Predicted vs actual</span>
      <span className="card-score-num">
        {hits}
        <span className="muted">/{decided}</span>
      </span>
      <span className="small">
        winners called correctly
        {v.length > decided && <span className="muted"> · {v.length - decided} void or 50/50</span>}
      </span>
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
      <CardScore bouts={data.bouts} />
      <div className="section">
        {data.bouts.map((b, i) => (
          <Bout key={b.bout_id} b={b} date={data.date} i={i} />
        ))}
      </div>
    </>
  );
}

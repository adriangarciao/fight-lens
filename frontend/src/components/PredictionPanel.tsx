import { api, type Method, type Prediction, type Reason } from "../api";
import { fmtDate } from "../format";
import { useAsync } from "../useAsync";

const METHOD_NAME: { [m in Method]: string } = { "KO/TKO": "KO/TKO", SUB: "Submission", DEC: "Decision" };
const ROUNDS_SOURCE: { [k: string]: string } = {
  source: "published",
  "rule:title": "inferred: title fight",
  "rule:main_event": "inferred: main event",
  "rule:standard": "inferred: standard bout",
  request: "chosen",
};

const pct = (p: number) => `${(p * 100).toFixed(p < 0.1 ? 1 : 0)}%`;

export function SplitBar({ a, b, compact = false }: { a: number; b: number; compact?: boolean }) {
  return (
    <div className={`split ${compact ? "compact" : ""}`} role="img" aria-label={`${pct(a)} to ${pct(b)}`}>
      <span className="split-a" style={{ width: `${a * 100}%` }} />
      <span className="split-b" style={{ width: `${b * 100}%` }} />
    </div>
  );
}

function Reasons({ reasons, side, name }: { reasons: Reason[]; side: "a" | "b"; name: string }) {
  const max = Math.max(0.01, ...reasons.map((r) => r.contribution));
  return (
    <div>
      <h3 className={`side-${side}`} style={{ marginBottom: 8 }}>Favouring {name}</h3>
      {reasons.length === 0 ? (
        <p className="empty">No input pushes meaningfully toward {name}.</p>
      ) : (
        <ol className="reasons">
          {reasons.map((r) => (
            <li key={r.feature}>
              <div className="reason-head">
                <span>{r.label}</span>
                <span className={`weight side-${side}`} style={{ width: `${(r.contribution / max) * 48}px` }} aria-hidden />
              </div>
              <div className="mono small muted">{r.detail}</div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Panel({ p }: { p: Prediction }) {
  const { fighter_a: A, fighter_b: B } = p;
  const rows = p.outcomes.map((o) => ({ ...o, side: o.fighter_id === A.id ? "a" : "b", name: o.fighter_id === A.id ? A.name : B.name }));
  const maxP = Math.max(...rows.map((r) => r.probability));
  return (
    <div className="prediction">
      {p.in_sample && (
        <div className="flag big-flag">
          Hindsight estimate: this model was trained on data that includes this date's results, so it isn't a genuine
          pre-fight prediction.
        </div>
      )}
      <div className="win-line">
        <div className="win side-a">
          <span className="big-pct">{pct(p.win_probability.a)}</span>
          <span className="kicker">{A.name}</span>
        </div>
        <div className="win side-b right">
          <span className="big-pct">{pct(p.win_probability.b)}</span>
          <span className="kicker">{B.name}</span>
        </div>
      </div>
      <SplitBar a={p.win_probability.a} b={p.win_probability.b} />
      <div className="pred-meta mono small muted">
        <span>model {p.model_version}</span>
        <span>features {p.feature_set_version}</span>
        <span>as of {fmtDate(p.as_of)}</span>
        <span>
          {p.scheduled_rounds ?? "?"} rounds ({ROUNDS_SOURCE[p.scheduled_rounds_source ?? ""] ?? "unknown"})
        </span>
        <span className={`conf conf-${p.data_confidence.level}`}>data confidence: {p.data_confidence.level}</span>
      </div>

      <div className="two-col section" style={{ marginTop: 28 }}>
        <div>
          <h3 style={{ marginBottom: 4 }}>How it ends</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Each row is the chance of that exact outcome. The six rows add up to 100%. They aren't the share of a
            fighter's wins.
          </p>
          <table className="outcomes">
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.fighter_id}-${r.method}`}>
                  <td className={`side-${r.side}`}>{r.name}</td>
                  <td className="muted">by {METHOD_NAME[r.method]}</td>
                  <td className="bar-cell">
                    <span className={`obar bg-${r.side}`} style={{ width: `${(r.probability / maxP) * 100}%` }} />
                  </td>
                  <td className="mono num">{pct(r.probability)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3 style={{ marginBottom: 4 }}>Major unknowns</h3>
          <ul className="unknowns">
            {p.unknowns.map((u) => <li key={u}>{u}</li>)}
          </ul>
          <h3 style={{ margin: "20px 0 4px" }}>Data confidence</h3>
          <ul className="unknowns">
            {p.data_confidence.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
          <p className="small muted">This rates how complete the data is. It isn't a measure of how sure the prediction is.</p>
        </div>
      </div>

      <div className="two-col section">
        <Reasons reasons={p.reasons.a} side="a" name={A.name} />
        <Reasons reasons={p.reasons.b} side="b" name={B.name} />
      </div>
      <p className="disclaimer" style={{ marginTop: 16 }}>
        {p.disclaimer} Reasons are the model's own per-input contributions, grouped where inputs overlap.
      </p>
    </div>
  );
}

interface Props {
  a: number;
  b: number;
  asOf?: string;
  rounds: 3 | 5;
  title: boolean;
}

export function PredictionPanel({ a, b, asOf, rounds, title }: Props) {
  const { data, error, loading } = useAsync(() => api.predictMatchup(a, b, asOf, rounds, title), [a, b, asOf, rounds, title]);
  if (loading && !data) return <p className="loading">Running model</p>;
  if (error) {
    return (
      <div className="prediction-pending">
        <span className="big">—%</span>
        <span className="small">
          <strong>No model estimate available.</strong> {error}
        </span>
      </div>
    );
  }
  return data ? <Panel p={data} /> : null;
}

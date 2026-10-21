import type { FightRecord } from "../api";
import { fmtDate, fmtDays, fmtFinish, fmtRecord, method } from "../format";

export function Timeline({ fights, empty = "No prior UFC bouts." }: { fights: FightRecord[]; empty?: string }) {
  if (!fights.length) return <p className="empty">{empty}</p>;
  return (
    <ol className="timeline">
      {fights.map((f) => (
        <li key={f.bout_id}>
          <span className={`res ${f.result}`} aria-label={f.result}>{f.result}</span>
          <div>
            <div className="opp">{f.opponent.name}</div>
            <div className="mono small muted">
              opp. {fmtRecord(f.opponent_record_before)} going in
            </div>
            <div className="small">
              {method(f.method, f.method_detail)}
              {f.end_round != null && <span className="muted"> · {fmtFinish(f.end_round, f.end_time_seconds)}</span>}
              {f.is_title_bout && <span className="badge hot" style={{ marginLeft: 8 }}>Title</span>}
            </div>
          </div>
          <div className="when">
            {fmtDate(f.event.date)}
            <br />
            {fmtDays(f.days_before_as_of)} ago
            <br />
            {f.division ?? ""}
          </div>
        </li>
      ))}
    </ol>
  );
}

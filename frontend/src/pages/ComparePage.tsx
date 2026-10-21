import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type FighterRef, type FighterSummary, type MatchupComparison } from "../api";
import { FighterPicker } from "../components/FighterPicker";
import { PredictionPanel } from "../components/PredictionPanel";
import { Timeline } from "../components/Timeline";
import { fmtDate, fmtDays, fmtFinish, fmtHeight, fmtRecord, method } from "../format";
import { useAsync } from "../useAsync";

const NA = <span className="na">unavailable</span>;
const or = (v: ReactNode | null | undefined) => (v == null || v === "" ? NA : v);

const LAYOFF: { [k: string]: string } = {
  debut: "UFC debut",
  long_layoff: "1y+ layoff",
  short_turnaround: "Short turnaround",
  normal: "",
};

const TAPE: [string, (s: FighterSummary) => ReactNode][] = [
  ["Age", (s) => or(s.physical.age_years)],
  ["Height", (s) => or(fmtHeight(s.physical.height_in))],
  ["Reach", (s) => or(s.physical.reach_in && `${s.physical.reach_in}″`)],
  ["Stance", (s) => or(s.physical.stance)],
  ["Division", (s) => or(s.latest_division)],
  ["UFC record", (s) => fmtRecord(s.record)],
  ["Last 5", (s) => fmtRecord(s.last5_record)],
  ["Coming off", (s) => or(s.coming_off)],
  ["Streak", (s) => (s.streak.kind === "none" ? "—" : `${s.streak.count}${s.streak.kind}`)],
  [
    "Since last fight",
    (s) => (
      <>
        {or(fmtDays(s.activity.days_since_last_fight))}
        {LAYOFF[s.activity.layoff_flag] && <span className="muted small"> · {LAYOFF[s.activity.layoff_flag]}</span>}
      </>
    ),
  ],
  ["Fights 12 / 24 mo", (s) => `${s.activity.fights_last_12_months} / ${s.activity.fights_last_24_months}`],
  ["UFC debut", (s) => (s.ufc_debut ? `${fmtDate(s.ufc_debut)} (${s.years_in_ufc}y)` : NA)],
];

function Comparison({ m, rounds, title }: { m: MatchupComparison; rounds: 3 | 5; title: boolean }) {
  const { fighter_a: A, fighter_b: B } = m;
  const nameOf = (id: string) => (Number(id) === A.fighter.id ? A.fighter.name : B.fighter.name);
  return (
    <>
      <div className="tape-header">
        <div className="fname a">{A.fighter.name}</div>
        <div className="vs">VS</div>
        <div className="fname b">{B.fighter.name}</div>
      </div>

      <PredictionPanel a={A.fighter.id} b={B.fighter.id} asOf={m.as_of} rounds={rounds} title={title} />

      <div className="section-head section">
        <h2>Tale of the tape</h2>
        <span className="mono small muted">UFC bouts before {fmtDate(m.as_of)}</span>
      </div>

      <table className="tape">
        <tbody>
          {TAPE.map(([label, get]) => (
            <tr key={label}>
              <td>{get(A)}</td>
              <td className="label">{label}</td>
              <td>{get(B)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="two-col">
        <div className="flags">{A.limited_data.map((f) => <span className="flag" key={f}>{f}</span>)}</div>
        <div className="flags">{B.limited_data.map((f) => <span className="flag" key={f}>{f}</span>)}</div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Last five</h2>
          <span className="mono small muted">opponent record is as of that bout</span>
        </div>
        <div className="two-col">
          <div>
            <h3 style={{ color: "var(--a)", marginBottom: 8 }}>{A.fighter.name}</h3>
            <Timeline fights={A.recent_fights} />
          </div>
          <div>
            <h3 style={{ color: "var(--b)", marginBottom: 8 }}>{B.fighter.name}</h3>
            <Timeline fights={B.recent_fights} />
          </div>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Head to head</h2>
          <span className="mono small muted">{m.head_to_head.length} prior meeting(s)</span>
        </div>
        {m.head_to_head.length === 0 && <p className="empty">These fighters have not met in the UFC.</p>}
        {m.head_to_head.map((x) => (
          <div className="meeting" key={x.bout_id}>
            <div className="kicker">
              {fmtDate(x.event.date)} · {fmtDays(x.days_before_as_of)} ago · {x.event.name}
            </div>
            <h3 style={{ marginTop: 6 }}>
              {x.winner ? `${x.winner.name} won` : x.outcome === "draw" ? "Draw" : "No contest"}
            </h3>
            <div className="small">
              {method(x.method, x.method_detail)} <span className="muted">{fmtFinish(x.end_round, x.end_time_seconds)}</span> ·{" "}
              {x.division}
            </div>
            <div className="mono small muted" style={{ marginTop: 6 }}>
              {Object.entries(x.fights_since).map(([id, n]) => (
                <div key={id}>
                  {nameOf(id)}: {n} UFC bout(s) since
                  {x.division_changes[id]?.length ? `; since fought at ${x.division_changes[id].join(", ")}` : ""}
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Common opponents</h2>
          <span className="mono small muted">context, not proof</span>
        </div>
        {m.common_opponents.length === 0 && <p className="empty">No shared UFC opponents.</p>}
        {m.common_opponents.map((c) => (
          <div className="common" key={c.opponent.id}>
            <h3>{c.opponent.name}</h3>
            {c.limited_comparison.length > 0 && (
              <div className="flags">
                <span className="flag">Limited comparison</span>
                {c.limited_comparison.map((l) => <span className="flag" key={l}>{l}</span>)}
              </div>
            )}
            <div className="common-grid">
              <Timeline fights={c.fighter_a.fights} />
              <Timeline fights={c.fighter_b.fights} />
            </div>
          </div>
        ))}
      </section>

      <ul className="notes">
        {m.notes.map((n) => <li key={n}>{n}</li>)}
      </ul>
    </>
  );
}

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const aId = Number(params.get("a")) || null;
  const bId = Number(params.get("b")) || null;
  const asOf = params.get("asOf") ?? undefined;
  const rounds: 3 | 5 = params.get("rounds") === "5" ? 5 : 3;
  const title = params.get("title") === "1";
  const [a, setA] = useState<FighterRef | null>(null);
  const [b, setB] = useState<FighterRef | null>(null);

  const { data, error, loading } = useAsync(
    () => (aId && bId ? api.matchup(aId, bId, asOf) : null),
    [aId, bId, asOf],
  );

  useEffect(() => {
    if (data) {
      setA(data.fighter_a.fighter);
      setB(data.fighter_b.fighter);
    }
  }, [data]);

  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <>
      <div className="kicker">Matchup breakdown</div>
      <h1>Tale of the tape</h1>
      <div className="section pickers" style={{ marginTop: 24 }}>
        <FighterPicker side="a" label="Fighter A" value={a} onChange={(f) => (setA(f), update("a", String(f.id)))} />
        <span className="vs">VS</span>
        <FighterPicker side="b" label="Fighter B" value={b} onChange={(f) => (setB(f), update("b", String(f.id)))} />
      </div>
      <div className="asof mono small">
        <label htmlFor="asof">As of</label>
        <input id="asof" type="date" value={asOf ?? ""} onChange={(e) => update("asOf", e.target.value || null)} />
        <span className="muted">{asOf ? "only bouts before this date count" : "today"}</span>
        <span className="rounds-toggle" role="group" aria-label="Scheduled rounds">
          {([3, 5] as const).map((r) => (
            <button key={r} type="button" aria-pressed={rounds === r} onClick={() => update("rounds", String(r))}>
              {r} rds
            </button>
          ))}
        </span>
        {(aId || bId) && (
          <button
            className="btn ghost"
            type="button"
            onClick={() => (setA(null), setB(null), setParams(new URLSearchParams()))}
          >
            Clear
          </button>
        )}
      </div>

      {!aId || !bId ? (
        <p className="empty">Pick two fighters, scheduled or hypothetical.</p>
      ) : loading && !data ? (
        <p className="loading">Pulling records</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : data ? (
        <Comparison m={data} rounds={rounds} title={title} />
      ) : null}
    </>
  );
}

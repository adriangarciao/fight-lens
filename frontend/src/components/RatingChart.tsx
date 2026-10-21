import { useMemo, useState } from "react";
import type { RatingPoint } from "../api";
import { fmtDate, METHOD_LABEL } from "../format";
import { Legend, Mark, niceTicks, useWidth } from "./chartParts";

interface Series {
  side: "a" | "b";
  name: string;
  points: RatingPoint[];
}

const START = 1500;
const H = 240;
const M = { top: 12, right: 52, bottom: 24, left: 40 };
const RESULT_WORD: { [r: string]: string } = { W: "beat", L: "lost to", D: "drew with", NC: "no contest vs" };

const t = (iso: string) => new Date(`${iso}T00:00:00`).getTime();

/**
 * Strength rating (Elo) over time for both fighters, as the model computed it before the as-of
 * date. Ratings only change at fights, so the series are step lines with a mark per bout.
 */
export function RatingChart({ a, b, asOf, eloK }: { a: Series; b: Series; asOf: string; eloK: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ side: "a" | "b"; i: number } | null>(null);
  const series = [a, b].filter((s) => s.points.length > 0);

  const geo = useMemo(() => {
    const all = series.flatMap((s) => s.points);
    const end = t(asOf);
    const start = all.length ? Math.min(...all.map((p) => t(p.date))) : end - 365 * 864e5;
    const pad = (end - start) * 0.02 || 864e5 * 30;
    const values = [START, ...all.flatMap((p) => [p.elo, p.elo_before])];
    const yTicks = niceTicks(Math.min(...values) - 15, Math.max(...values) + 15, 4);
    const y0 = Math.min(yTicks[0], Math.min(...values) - 15);
    const y1 = Math.max(yTicks[yTicks.length - 1], Math.max(...values) + 15);
    const iw = width - M.left - M.right;
    const ih = H - M.top - M.bottom;
    const x = (ms: number) => M.left + ((ms - (start - pad)) / (end - (start - pad))) * iw;
    const y = (v: number) => M.top + (1 - (v - y0) / (y1 - y0)) * ih;
    const years: number[] = [];
    for (let yr = new Date(start).getFullYear() + 1; yr <= new Date(end).getFullYear(); yr++) years.push(yr);
    const step = Math.ceil(years.length / Math.max(2, Math.floor(iw / 70)));
    return { x, y, end, yTicks, years: years.filter((_, i) => i % step === 0), iw, ih };
  }, [series, width, asOf]);

  const path = (s: Series) => {
    const { x, y, end } = geo;
    const p = s.points;
    let d = `M${x(t(p[0].date))},${y(p[0].elo_before)}`;
    p.forEach((pt) => (d += ` H${x(t(pt.date))} V${y(pt.elo)}`));
    return `${d} H${x(end)}`;
  };

  // Snap the hover to the nearest bout of either fighter.
  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const mx = e.clientX - box.left;
    let best: { side: "a" | "b"; i: number; d: number } | null = null;
    for (const s of series) {
      s.points.forEach((p, i) => {
        const d = Math.abs(geo.x(t(p.date)) - mx);
        if (!best || d < best.d) best = { side: s.side, i, d };
      });
    }
    setHover(best);
  };

  const hovered = hover ? (hover.side === "a" ? a : b).points[hover.i] : null;
  const ratingAt = (s: Series, when: string) => {
    const before = s.points.filter((p) => t(p.date) <= t(when));
    return before.length ? before[before.length - 1].elo : s.points.length ? START : null;
  };

  if (series.length === 0) {
    return <p className="empty">Neither fighter has prior UFC bouts, so there is no rating history yet.</p>;
  }

  return (
    <div className="chart" ref={ref}>
      <Legend a={a.name} b={b.name} />
      <svg width={width} height={H} role="img" aria-label={`Strength rating over time for ${a.name} and ${b.name}`}>
        <g className="grid">
          {geo.yTicks.map((v) => (
            <line key={v} x1={M.left} x2={M.left + geo.iw} y1={geo.y(v)} y2={geo.y(v)} />
          ))}
        </g>
        <g className="axis">
          {geo.yTicks.map((v) => (
            <text key={v} x={M.left - 6} y={geo.y(v) + 3} textAnchor="end">
              {v}
            </text>
          ))}
          {geo.years.map((yr) => (
            <text key={yr} x={geo.x(new Date(yr, 0, 1).getTime())} y={H - 6} textAnchor="middle">
              {yr}
            </text>
          ))}
        </g>
        <line className="ref" x1={M.left} x2={M.left + geo.iw} y1={geo.y(START)} y2={geo.y(START)} />
        <text className="ref-label" x={M.left + geo.iw - 4} y={geo.y(START) - 4} textAnchor="end">
          debut rating {START}
        </text>
        {hovered && (
          <line className="crosshair" x1={geo.x(t(hovered.date))} x2={geo.x(t(hovered.date))} y1={M.top} y2={M.top + geo.ih} />
        )}
        {series.map((s) => (
          <path key={s.side} className={`series ${s.side}`} d={path(s)} />
        ))}
        {series.map((s) =>
          s.points.map((p, i) => (
            <Mark
              key={`${s.side}${i}`}
              side={s.side}
              x={geo.x(t(p.date))}
              y={geo.y(p.elo)}
              size={hover && hover.side === s.side && hover.i === i ? 12 : 8}
            />
          )),
        )}
        {series.map((s) => {
          const last = s.points[s.points.length - 1];
          const other = series.find((o) => o.side !== s.side);
          const otherLast = other?.points[other.points.length - 1];
          // Nudge end labels apart when the two lines finish close together.
          const clash = otherLast && Math.abs(geo.y(last.elo) - geo.y(otherLast.elo)) < 12;
          const dy = clash ? (last.elo >= (otherLast?.elo ?? 0) ? -6 : 6) : 0;
          return (
            <text key={s.side} className="end-label" x={geo.x(geo.end) + 6} y={geo.y(last.elo) + 4 + dy}>
              {Math.round(last.elo)}
            </text>
          );
        })}
        <rect
          className="hit"
          x={M.left}
          y={M.top}
          width={geo.iw}
          height={geo.ih}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      {hovered && hover && (
        <div
          className="tooltip"
          style={(() => {
            // Sit beside the crosshair, flipping to its left on the right half so the hovered
            // mark and the end labels stay visible.
            const cx = geo.x(t(hovered.date));
            const tooltipW = 270;
            const left = cx > width / 2 ? cx - 12 - tooltipW : cx + 12;
            return { left: Math.max(0, Math.min(left, width - tooltipW)), top: 28 };
          })()}
        >
          <div className="t-head">{fmtDate(hovered.date)}</div>
          <div className="t-row">
            <svg width={12} height={12} className="swatch">
              <Mark side={hover.side} x={6} y={6} />
            </svg>
            {(hover.side === "a" ? a : b).name} {RESULT_WORD[hovered.result]} {hovered.opponent.name}
          </div>
          <div className="muted">
            {hovered.method ? `${METHOD_LABEL[hovered.method] ?? hovered.method} · ` : ""}
            {Math.round(hovered.elo_before)} → {Math.round(hovered.elo)} ({hovered.elo >= hovered.elo_before ? "+" : ""}
            {Math.round(hovered.elo - hovered.elo_before)})
          </div>
          {(() => {
            const other = hover.side === "a" ? b : a;
            const r = ratingAt(other, hovered.date);
            return r == null ? null : (
              <div className="t-row muted">
                <svg width={12} height={12} className="swatch">
                  <Mark side={other.side} x={6} y={6} />
                </svg>
                {other.name}: {Math.round(r)}
              </div>
            );
          })()}
        </div>
      )}
      <details className="chart-table">
        <summary>Rating data table</summary>
        <table>
          <thead>
            <tr>
              <th>Fighter</th>
              <th>Date</th>
              <th>Result</th>
              <th>Rating</th>
            </tr>
          </thead>
          <tbody>
            {series.flatMap((s) =>
              s.points.map((p, i) => (
                <tr key={`${s.side}${i}`}>
                  <td>{s.name}</td>
                  <td>{fmtDate(p.date)}</td>
                  <td>
                    {RESULT_WORD[p.result]} {p.opponent.name}
                  </td>
                  <td>
                    {Math.round(p.elo_before)} → {Math.round(p.elo)}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </details>
      <p className="small muted">
        Elo rating (K = {eloK}) from UFC results only: beating a higher-rated opponent moves it more. Everyone debuts at{" "}
        {START}.
      </p>
    </div>
  );
}

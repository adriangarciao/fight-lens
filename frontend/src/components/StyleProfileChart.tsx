import { useState } from "react";
import type { LeagueAverages, StyleStats } from "../api";
import { Legend, Mark, useWidth } from "./chartParts";

type Key = keyof LeagueAverages;

// Every row reads the same way: further right = more of that skill than the league average.
const ROWS: { key: Key; label: string; fmt: (x: number) => string }[] = [
  { key: "slpm", label: "Striking output", fmt: (x) => `${x.toFixed(2)}/min` },
  { key: "str_acc", label: "Striking accuracy", fmt: (x) => `${Math.round(x * 100)}%` },
  { key: "str_def", label: "Striking defense", fmt: (x) => `${Math.round(x * 100)}%` },
  { key: "kd15", label: "Knockdowns", fmt: (x) => `${x.toFixed(2)}/15m` },
  { key: "td15", label: "Takedowns", fmt: (x) => `${x.toFixed(2)}/15m` },
  { key: "td_acc", label: "Takedown accuracy", fmt: (x) => `${Math.round(x * 100)}%` },
  { key: "td_def", label: "Takedown defense", fmt: (x) => `${Math.round(x * 100)}%` },
  { key: "ctrl_share", label: "Control time", fmt: (x) => `${Math.round(x * 100)}%` },
  { key: "sub15", label: "Sub attempts", fmt: (x) => `${x.toFixed(2)}/15m` },
];
const ROW_H = 30;
const MAX_INDEX = 300;

interface Side {
  name: string;
  style: StyleStats | null;
}

/**
 * Each stat as an index of the league average at the as-of date (100 = average), so stats with
 * different units share one honest axis. Values are raw career rates, the same numbers as the
 * table below.
 */
export function StyleProfileChart({ a, b, league }: { a: Side; b: Side; league: LeagueAverages }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const labelW = width < 480 ? 124 : 140; // fits "Takedown accuracy" in 11px mono
  const right = 16;
  const top = 18;
  const iw = width - labelW - right;
  const height = top + ROWS.length * ROW_H + 8;

  const index = (s: Side, key: Key) => {
    const v = s.style?.[key];
    const avg = league[key];
    return v == null || !avg ? null : (v / avg) * 100;
  };
  const maxIdx = Math.min(
    MAX_INDEX,
    Math.max(200, ...ROWS.flatMap((r) => [index(a, r.key) ?? 0, index(b, r.key) ?? 0]).map((v) => Math.ceil(v / 50) * 50)),
  );
  const x = (v: number) => labelW + (Math.min(v, maxIdx) / maxIdx) * iw;
  const ticks = Array.from({ length: maxIdx / 50 + 1 }, (_, i) => i * 50).filter((v) => width >= 480 || v % 100 === 0);

  if (!a.style && !b.style) {
    return <p className="empty">No per-fight stats yet for either fighter.</p>;
  }

  const row = active == null ? null : ROWS[active];
  return (
    <div className="chart" ref={ref}>
      <Legend a={a.name} b={b.name} />
      <svg width={width} height={height} role="img" aria-label="Style profile relative to league average">
        <g className="grid">
          {ticks.map((v) => (
            <line key={v} x1={x(v)} x2={x(v)} y1={top - 4} y2={height - 8} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((v) => (
            <text key={v} x={x(v)} y={top - 7} textAnchor="middle">
              {v}
            </text>
          ))}
        </g>
        <line className="ref" x1={x(100)} x2={x(100)} y1={top - 4} y2={height - 8} />
        {ROWS.map((r, i) => {
          const cy = top + i * ROW_H + ROW_H / 2;
          const ia = index(a, r.key);
          const ib = index(b, r.key);
          // Offset the marks vertically when they would overlap.
          const close = ia != null && ib != null && Math.abs(x(ia) - x(ib)) < 10;
          return (
            <g
              key={r.key}
              tabIndex={0}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              aria-label={`${r.label}: ${a.name} ${ia == null ? "no data" : Math.round(ia)}, ${b.name} ${ib == null ? "no data" : Math.round(ib)} (100 = league average)`}
            >
              <rect className={`row-band ${active === i ? "active" : ""}`} x={0} y={cy - ROW_H / 2} width={width} height={ROW_H} />
              <text className="row-label" x={0} y={cy + 4}>
                {r.label}
              </text>
              {ia != null && ib != null && (
                <line x1={x(ia)} x2={x(ib)} y1={cy} y2={cy} stroke="var(--ink-3)" strokeWidth={1} />
              )}
              {ia != null && <Mark side="a" x={x(ia)} y={cy - (close ? 4 : 0)} size={10} />}
              {ib != null && <Mark side="b" x={x(ib)} y={cy + (close ? 4 : 0)} size={10} />}
              {[ia, ib].some((v) => v != null && v > maxIdx) && (
                <text className="row-label" x={labelW + iw + 4} y={cy + 4}>
                  ›
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {row && active != null && (
        <div className="tooltip" style={{ left: Math.min(labelW, width - 270), top: top + (active + 1) * ROW_H + 18 }}>
          <div className="t-head">{row.label}</div>
          {([["a", a], ["b", b]] as const).map(([side, s]) => {
            const v = s.style?.[row.key];
            const idx = index(s, row.key);
            return (
              <div className="t-row" key={side}>
                <svg width={12} height={12} className="swatch">
                  <Mark side={side} x={6} y={6} />
                </svg>
                {s.name}: {v == null ? "no data" : `${row.fmt(v)} (${Math.round(idx!)})`}
              </div>
            );
          })}
          <div className="muted">League average: {row.fmt(league[row.key])} (100)</div>
        </div>
      )}
      <p className="small muted">
        100 = league average at this date. Career UFC rates; the exact numbers are in the table below.
      </p>
    </div>
  );
}

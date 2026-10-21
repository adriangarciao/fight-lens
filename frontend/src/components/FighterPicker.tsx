import { useEffect, useState } from "react";
import { api, type FighterRef, type FighterSearchResult } from "../api";
import { fmtRecord } from "../format";

interface Props {
  side: "a" | "b";
  label: string;
  value: FighterRef | null;
  onChange: (f: FighterRef) => void;
}

export function FighterPicker({ side, label, value, onChange }: Props) {
  const [q, setQ] = useState(value?.name ?? "");
  const [results, setResults] = useState<FighterSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);

  useEffect(() => setQ(value?.name ?? ""), [value?.id]);

  useEffect(() => {
    if (!open || q.trim().length < 2) {
      setResults([]);
      return;
    }
    let live = true;
    const t = setTimeout(() => {
      api.searchFighters(q.trim()).then((r) => live && (setResults(r), setCursor(0))).catch(() => {});
    }, 150);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q, open]);

  const choose = (r: FighterSearchResult) => {
    onChange({ id: r.id, name: r.name });
    setQ(r.name);
    setOpen(false);
  };

  return (
    <div className={`picker ${side}`}>
      <label className="kicker" htmlFor={`picker-${side}`}>{label}</label>
      <input
        id={`picker-${side}`}
        value={q}
        placeholder="Search fighter"
        autoComplete="off"
        role="combobox"
        aria-expanded={open && results.length > 0}
        onFocus={(e) => (e.target.select(), setOpen(true))}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => (setQ(e.target.value), setOpen(true))}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, results.length - 1));
          else if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
          else if (e.key === "Enter" && results[cursor]) choose(results[cursor]);
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && results.length > 0 && (
        <ul className="results" role="listbox">
          {results.map((r, i) => (
            <li key={r.id}>
              <button type="button" aria-selected={i === cursor} onMouseDown={() => choose(r)}>
                <span>{r.name}</span>
                <span className="mono small muted">
                  {r.latest_division ?? "—"} · {fmtRecord(r.record)}
                  {r.last_fight_date ? ` · ${r.last_fight_date.slice(0, 4)}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

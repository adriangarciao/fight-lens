import { useEffect, useRef, useState } from "react";

/** Container width, tracked with ResizeObserver so SVG text never scales. */
export function useWidth<T extends HTMLElement>(initial = 640) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/**
 * Fighter A is a circle, fighter B a square: identity never relies on color alone.
 * Marks are 8px+ with a 2px surface ring so overlapping marks stay distinct.
 */
export function Mark({ side, x, y, size = 9, className = "" }: { side: "a" | "b"; x: number; y: number; size?: number; className?: string }) {
  return side === "a" ? (
    <circle className={`mark a ring ${className}`} cx={x} cy={y} r={size / 2} />
  ) : (
    <rect className={`mark b ring ${className}`} x={x - size / 2} y={y - size / 2} width={size} height={size} rx={1.5} />
  );
}

export function Legend({ a, b }: { a: string; b: string }) {
  return (
    <div className="legend" aria-hidden>
      {(["a", "b"] as const).map((side) => (
        <span key={side}>
          <svg width={12} height={12} className="swatch">
            <Mark side={side} x={6} y={6} size={9} />
          </svg>
          {side === "a" ? a : b}
        </span>
      ))}
    </div>
  );
}

export function niceTicks(lo: number, hi: number, target = 5): number[] {
  const span = hi - lo || 1;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= target) ?? 10 * mag;
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) ticks.push(Math.round(t * 1000) / 1000);
  return ticks;
}

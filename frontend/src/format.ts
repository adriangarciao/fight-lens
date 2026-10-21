import type { Record } from "./api";

export const fmtRecord = (r: Record) =>
  `${r.wins}-${r.losses}-${r.draws}${r.no_contests ? ` (${r.no_contests} NC)` : ""}`;

export const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

export const fmtClock = (seconds: number | null) =>
  seconds == null ? "" : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

export const fmtFinish = (round: number | null, seconds: number | null) =>
  round == null ? "" : `R${round} ${fmtClock(seconds)}`.trim();

export const fmtHeight = (inches: number | null) =>
  inches == null ? null : `${Math.floor(inches / 12)}′${Math.round(inches % 12)}″`;

export const fmtDays = (days: number | null) => {
  if (days == null) return null;
  if (days < 60) return `${days}d`;
  if (days < 730) return `${Math.round(days / 30.44)}mo`;
  return `${(days / 365.25).toFixed(1)}y`;
};

export const METHOD_LABEL: { [k: string]: string } = {
  "KO/TKO": "KO/TKO",
  SUB: "Submission",
  DEC: "Decision",
  DQ: "DQ",
  OVERTURNED: "Overturned",
  CNC: "Could not continue",
  OTHER: "Other",
};

export const method = (m: string | null, detail: string | null) =>
  detail && m === "DEC" ? detail.replace("Decision - ", "Dec · ") : m ? METHOD_LABEL[m] ?? m : "—";

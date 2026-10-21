// Mirrors backend/app/schemas. Keep in sync with the OpenAPI document at /docs.

export type Result = "W" | "L" | "D" | "NC";

export interface FighterRef {
  id: number;
  name: string;
}

export interface Record {
  wins: number;
  losses: number;
  draws: number;
  no_contests: number;
}

export interface EventRef {
  id: number;
  name: string;
  date: string;
  location: string | null;
}

export interface FightRecord {
  bout_id: number;
  event: EventRef;
  opponent: FighterRef;
  opponent_record_before: Record;
  result: Result;
  method: string | null;
  method_detail: string | null;
  finish_details: string | null;
  end_round: number | null;
  end_time_seconds: number | null;
  scheduled_rounds: number | null;
  division: string | null;
  is_title_bout: boolean;
  days_before_as_of: number;
}

export interface FighterSummary {
  fighter: FighterRef;
  as_of: string;
  physical: {
    age_years: number | null;
    height_in: number | null;
    reach_in: number | null;
    stance: string | null;
  };
  record: Record;
  last5_record: Record;
  coming_off: Result | null;
  streak: { kind: "W" | "L" | "D" | "none"; count: number };
  activity: {
    days_since_last_fight: number | null;
    fights_last_12_months: number;
    fights_last_24_months: number;
    layoff_flag: "debut" | "long_layoff" | "short_turnaround" | "normal";
  };
  ufc_debut: string | null;
  years_in_ufc: number | null;
  latest_division: string | null;
  recent_fights: FightRecord[];
  limited_data: string[];
}

export interface Meeting {
  bout_id: number;
  event: EventRef;
  winner: FighterRef | null;
  outcome: string;
  method: string | null;
  method_detail: string | null;
  end_round: number | null;
  end_time_seconds: number | null;
  division: string | null;
  days_before_as_of: number;
  division_changes: { [fighterId: string]: string[] };
  fights_since: { [fighterId: string]: number };
}

export interface CommonOpponent {
  opponent: FighterRef;
  fighter_a: { fights: FightRecord[] };
  fighter_b: { fights: FightRecord[] };
  gap_days: number;
  limited_comparison: string[];
}

export interface MatchupComparison {
  as_of: string;
  fighter_a: FighterSummary;
  fighter_b: FighterSummary;
  head_to_head: Meeting[];
  common_opponents: CommonOpponent[];
  notes: string[];
}

export interface FighterSearchResult {
  id: number;
  name: string;
  latest_division: string | null;
  last_fight_date: string | null;
  record: Record;
}

export interface EventSummary {
  id: number;
  name: string;
  date: string;
  location: string | null;
  bout_count: number;
  status: "scheduled" | "completed";
}

export interface CardBout {
  bout_id: number;
  fighter_1: FighterRef;
  fighter_2: FighterRef;
  record_1: Record;
  record_2: Record;
  division: string | null;
  weight_class_raw: string | null;
  scheduled_rounds: number | null;
  is_title_bout: boolean;
  status: "scheduled" | "completed";
  winner_id: number | null;
  outcome: string | null;
  method: string | null;
  end_round: number | null;
  end_time_seconds: number | null;
  scheduled_rounds_source: string | null;
  prediction: CardPrediction | null;
}

export interface CardPrediction {
  p_1: number;
  p_2: number;
  likely_outcome: string;
  likely_outcome_probability: number;
  model_version: string;
  generated_at: string;
}

export type Method = "KO/TKO" | "SUB" | "DEC";

export interface Reason {
  feature: string;
  label: string;
  detail: string;
  contribution: number;
}

export interface Prediction {
  fighter_a: FighterRef;
  fighter_b: FighterRef;
  as_of: string;
  scheduled_rounds: number | null;
  scheduled_rounds_source: string | null;
  model_version: string;
  feature_set_version: string;
  generated_at: string;
  stored: boolean;
  in_sample: boolean;
  win_probability: { a: number; b: number };
  method_given_win: { a: { [m in Method]: number }; b: { [m in Method]: number } };
  outcomes: { fighter_id: number; method: Method; probability: number }[];
  reasons: { a: Reason[]; b: Reason[] };
  unknowns: string[];
  data_confidence: { level: "high" | "medium" | "low"; reasons: string[] };
  disclaimer: string;
}

export interface EventDetail extends EventSummary {
  bouts: CardBout[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function get<T>(path: string, params?: { [k: string]: string | number | undefined }): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined) qs.set(k, String(v));
  return handle<T>(await fetch(`${path}${qs.size ? `?${qs}` : ""}`));
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  );
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`, res.status);
  }
  return res.json();
}

export const api = {
  upcomingEvents: () => get<EventSummary[]>("/api/events/upcoming"),
  recentEvents: () => get<EventSummary[]>("/api/events/recent"),
  event: (id: number) => get<EventDetail>(`/api/events/${id}`),
  searchFighters: (q: string) => get<FighterSearchResult[]>("/api/fighters/search", { q }),
  matchup: (a: number, b: number, asOf?: string) =>
    get<MatchupComparison>("/api/matchups", { fighterA: a, fighterB: b, asOf }),
  predictMatchup: (a: number, b: number, asOf: string | undefined, scheduledRounds: 3 | 5, titleBout: boolean) =>
    post<Prediction>("/api/predictions/matchup", { fighterA: a, fighterB: b, asOf, scheduledRounds, titleBout }),
};

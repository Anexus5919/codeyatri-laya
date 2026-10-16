// Shapes returned by arena_web.py. Every field may be missing in older logs, so most are optional.

export type Dir = "up" | "down" | "left" | "right";
export const DIRS: readonly Dir[] = ["up", "down", "left", "right"] as const;

export type Status = "live" | "idle" | "interrupted" | "finished";
export type EnvKind = "hosted" | "simulator" | "unknown";
export type GameState = Record<string, unknown>;
export type DirMap<T> = Partial<Record<Dir, T>>;

export interface Timing {
  decide_ms?: number;
  api_ms?: number;
  turn_ms?: number;
}

export interface TimingStat {
  last: number | null;
  mean: number | null;
  p95: number | null;
  n: number;
}

export interface SessionItem {
  game: string | null;
  session_id: string;
  mtime: number;
  age_s: number;
  steps: number;
  last_score: number | null;
  points: number | null;
  done: boolean;
  won: boolean | null;
  agent_name: string | null;
  status?: Status;
  env?: string | null;
  env_kind?: EnvKind;
  model?: string | null;
  model_source?: string | null;
  device?: string | null;
  design?: string | null;
  lines?: number;
  rejected?: number;
  fallbacks?: number;
  fallback_share?: number;
  decisions?: number;
  final_score?: number | null;
  points_source?: string;
  started_ts?: string | null;
  folder?: string;
  key?: string;
  source?: "arena" | "simulator";
  origin?: "runs" | "sim";
}

export interface SessionsResponse {
  root: string;
  sessions: SessionItem[];
  newest: string | null;
  newest_key?: string | null;
  sim_roots?: string[];
}

export interface DecisionEvent {
  step?: number;
  facts?: DirMap<string> | null;
  kinds?: DirMap<string> | null;
  p_true?: DirMap<number> | null;
  probabilities?: DirMap<number> | null;
  chosen?: Dir;
  source?: string;
  laya_choice?: Dir | null;
  reason?: string | null;
  decide_ms?: number | null;
  laya_ms?: number | null;
  ts?: string | null;
  state_text?: string | null;
}

export interface StepRecord {
  i: number;
  step: number;
  result: "applied" | "rejected" | string;
  action: Dir;
  source?: string;
  confidence?: number;
  probabilities?: DirMap<number>;
  n_questions?: number;
  timing?: Timing | null;
  ts?: string;
  hash?: string;
  state_before?: GameState | null;
  state_after?: GameState | null;
  event?: DecisionEvent | null;
  error?: unknown;
}

export interface Summary {
  game: string | null;
  lines: number;
  steps: number;
  rejected: number;
  fallbacks: number;
  fallback_share: number;
  timing: Record<"decide_ms" | "api_ms" | "turn_ms", TimingStat>;
  final_score: number | null;
  done: boolean;
  won: boolean | null;
  decisions: number;
  foods?: number;
  length?: number;
  target_points?: number;
  target_foods?: number;
  progress?: number;
  unlocked?: boolean;
  best_tile?: number;
  score?: number;
  target_tile?: number;
  points_computed: number | null;
  points: number | null;
  points_source: string;
  agent_name: string | null;
  env?: string | null;
  env_kind?: EnvKind;
  model?: string | null;
  model_source?: string | null;
  device?: string | null;
  design?: string | null;
  started_ts?: string | null;
  ended_ts?: string | null;
  source?: "arena" | "simulator";
  key?: string;
}

export interface SessionStart {
  session_id?: string;
  game?: string;
  agent_name?: string;
  env?: string;
  design?: string;
  offer?: string;
  model?: string;
  model_source?: string;
  device?: string;
  load?: Record<string, unknown> | null;
  first_response?: { state?: GameState; message?: string } & Record<string, unknown>;
  ts?: string;
}

export interface SessionEnd {
  score?: number | null;
  won?: boolean | null;
  steps?: number | null;
  done?: boolean | null;
  points?: number | null;
  ts?: string;
}

export interface HistoryResponse {
  session_id: string;
  key?: string;
  source?: "arena" | "simulator";
  game: string | null;
  folder: string;
  reset: boolean;
  after: number;
  next_after: number;
  total: number;
  records: StepRecord[];
  pending: DecisionEvent | null;
  events_count: number;
  bad_lines: number;
  session_start: SessionStart | null;
  session_end: SessionEnd | null;
  final: (Record<string, unknown> & { state?: GameState; score?: number; won?: boolean; steps?: number }) | null;
  summary: Summary;
  status: Status;
  live_window_s: number;
  interrupted_after_s: number;
  mtime: number;
  age_s: number;
}

export interface VerifyResult {
  ok: boolean | null;
  pending?: boolean;
  problems: string[];
  lines: number;
  chain_ok: boolean | null;
  applied?: number;
  fallbacks?: number;
  fallback_share?: number;
  final_score?: unknown;
  final_done?: unknown;
  session_id?: string;
  game?: string;
}

export interface StepDetail {
  session_id: string;
  i: number;
  line: Record<string, unknown> & { decision?: { questions?: string[] }; hash?: string; prev_hash?: string };
  event: (DecisionEvent & { state_text?: string }) | null;
  questions_by_dir: DirMap<string> | null;
}

import type { HistoryResponse, SessionsResponse, StepDetail, VerifyResult } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function getJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(url, { cache: "no-store", signal });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const body = (await r.json()) as { error?: string };
      if (body?.error) msg = body.error;
    } catch {
      // not JSON
    }
    throw new ApiError(msg, r.status);
  }
  return (await r.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  sessions: (signal?: AbortSignal) => getJSON<SessionsResponse>("api/sessions", signal),
  history: (id: string, after: number, limit = 400, signal?: AbortSignal) =>
    getJSON<HistoryResponse>(`api/history?id=${enc(id)}&after=${after}&limit=${limit}`, signal),
  verify: (id: string, signal?: AbortSignal, replay = false) =>
    getJSON<VerifyResult>(`api/verify?id=${enc(id)}${replay ? "&replay=1" : ""}`, signal),
  step: (id: string, i: number, signal?: AbortSignal) => getJSON<StepDetail>(`api/step?id=${enc(id)}&i=${i}`, signal),
};

// Full lines (questions and state text) are fetched on demand and kept per session
const stepCache = new Map<string, Promise<StepDetail>>();

export function loadStep(id: string, i: number): Promise<StepDetail> {
  const key = `${id}#${i}`;
  let p = stepCache.get(key);
  if (!p) {
    p = api.step(id, i).catch((e) => {
      stepCache.delete(key);
      throw e;
    });
    stepCache.set(key, p);
    if (stepCache.size > 400) {
      const first = stepCache.keys().next().value;
      if (first !== undefined) stepCache.delete(first);
    }
  }
  return p;
}

export function clearStepCache(): void {
  stepCache.clear();
}

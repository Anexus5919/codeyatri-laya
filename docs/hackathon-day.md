# Hackathon-day checklist

## Before the games are revealed

- [ ] `pytest -q` passes.
- [ ] `python scripts/smoke_laya.py --model english` runs from cache (no download) on the machine we will use.
- [ ] GPU decided: CUDA torch installed locally, or Colab notebook ready. CPU is about 400 ms per call.
- [ ] `.env` created from `.env.example`; `logs/` empty.
- [ ] Organiser questions from `docs/research.md` section 12 asked; answers recorded in `docs/decisions.md`.

## 1. API discovery (per game)

- [ ] Save the official API docs or OpenAPI file to `docs/api/<game>.md` (no tokens in it).
- [ ] Record: base URL, auth scheme, start/attach, state, move, result, score, session id, verification, rate limits, per-move time limit.
- [ ] Capture 3 to 5 real state responses into `fixtures/<game>/` (redacted). These are real captures, not invented.

## 2. Adapter

- [ ] Copy `src/laya_agent/game/hosted_template.py` to `src/laya_agent/game/<game>.py`.
- [ ] Fill every UNRESOLVED: paths, request bodies, turn field, idempotency header (send `decision_id` if supported), `reconcile` using the turn counter.
- [ ] `observe()`: validate required fields, read legal moves from the server (authoritative), build `Candidate`s with the exact API payload, write short factual descriptions with the decisive fact first, set `objective` and `priorities`.
- [ ] Register the game in `run.py:build_game`.
- [ ] Unit test `observe()` on the captured fixtures, including a terminal state.

## 3. Question design

- [ ] Check `usage.head_budget.cut` and `usage.truncated` on real states; shorten descriptions if anything is cut.
- [ ] Run each candidate design on the same captured states; record results in `docs/experiments.md`.
- [ ] More than about 20 legal moves: split the question or use laya's shortlist or tournament helpers, and log every stage.

## 4. First real run

- [ ] Start the viewer: `python -m laya_agent.viewer.web logs/`.
- [ ] Run: `python -m laya_agent.run --game <game>`.
- [ ] `python -m laya_agent.audit logs/<run>.jsonl` returns `"ok": true`.
- [ ] Compare our final score with the platform's verified score.

## 5. Iterate

- [ ] One change per experiment; several runs per configuration; record hypothesis, result, and keep or revert.
- [ ] Classify failures: state, mapping, Laya decision, wording, output reading, stale state, transport, duplicate risk, terminal detection, logging.

## 6. Keep the evidence

- [ ] Copy the best runs' logs to `runs/<game>/` and add their session ids and verified scores to `docs/results.md`.
- [ ] Commit and push after each stage clears.

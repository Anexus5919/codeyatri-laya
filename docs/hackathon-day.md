# Hackathon-day runbook (Genesis 2.0, 16 to 17 Oct 2026)

Games: stage 1 Snake, stage 2 2048, on https://topgameai.com/arena. Agent name is always `CodeYatri`.
Every real session is a permanent public record: never delete a log, never start a session casually.

## 0. Before any real run

- [ ] `.venv\Scripts\python -m pytest -q` passes (66 tests on 16 Oct).
- [ ] GPU in use: `.venv\Scripts\python -c "import torch;print(torch.cuda.is_available())"` prints True.
- [ ] `runs/` is empty or contains only real sessions. Simulator output lives in `runs_sim*/`, never in `runs/`.
- [ ] Mentor questions asked (section 4) and answers written into `docs/decisions.md`.

## 1. Run a real session (two terminals)

```
# terminal 1: the live viewer (must stay visible during judging)
.venv\Scripts\python -m laya_agent.viewer.arena_web runs --port 8770
# open http://127.0.0.1:8770

# terminal 2: one session
.venv\Scripts\python -m laya_agent.arena.runner --game snake
.venv\Scripts\python -m laya_agent.arena.runner --game 2048 --style v3
# fine-tuned checkpoint, once allowed:  --model path\to\checkpoint
```

What lands in `runs/<game>/`:
- `<session_id>.jsonl`: the submission log in the guide's exact format (hash chain, decision block, timing).
- `<session_id>.events.jsonl`: live events for the viewer (facts, raw P(true), reasons).
- `<session_id>.final.json`: the game's final response, saved the moment the game ends.

The runner prints the verifier report at the end (`"ok": true` means chain intact, steps contiguous,
decision blocks valid, fallback share within 10%, final response matches the last line).

## 2. After each session

- [ ] Note the session id, points and whether `ok` was true in `docs/results.md`.
- [ ] Snake at 600 or more: tell the organisers and ask for the 2048 unlock confirmation.
- [ ] Keep failed sessions. The rules treat hiding attempts as a fair-play breach.

## 3. Known facts about the arena (captured 16 Oct, 10:52 IST)

- `POST /api/arena/sessions {"game","agent_name"}` returns 201 with `session_id, state, done, won, score, steps, message`.
- `POST /api/arena/sessions/{id}/action {"action":"up"}` returns the same shape, or `{"error": ...}`.
- `GET /api/arena/sessions/{id}` returns the current session (used to reconcile a lost response).
- Snake state: `grid` (0 empty, 1 body, 2 food, 3 head), `snake` (head first), `food`, `direction`, `foodEaten`, `width` 12, `height` 12.
- 2048 state: `grid` 4x4, `score`, `best`. Caps: Snake 300 moves, 2048 2000 moves.

## 4. Questions for the mentor session (15:30)

1. Rejected moves: which `step` value do their log lines carry, given "no gaps in step"?
2. May we ask Laya only about legal directions (no reverse, no 2048 no-op) and log 0 for the rest with `source: laya`?
3. Are computed facts allowed in the question text (food distance, open space, corner kept), given they never choose the move?
4. Is a fine-tuned Laya checkpoint allowed? Our labels come from the stated priorities, not from a search.
5. How is the 2048 unlock confirmed, and do they read sessions by `session_id`?
6. Do idle sessions expire? Any rate limits?
7. Snake: can the head move into the cell the tail is leaving this turn? (Our facts assume no, the safe side.)
8. The 2048 page says "2048 tile = ~1000 pts" but the guide gives a formula. Which one is used for judging?

## 5. Current measured state (simulator, real Laya on the RTX 3050)

- Snake, zero-shot `noul_nodir`: 19 wins of 20 games, the one loss fixed by the moves-since-food fact; 70 to 110 ms per move.
- 2048, zero-shot: best tile 256 at most, no 512. A perfect reader of our facts reaches 512 in 75% of games, so fine-tuning on priority-reader labels is prepared (`data/ft2048`, Kaggle kernel `codeyatri-laya-2048-finetune`).

## 6. 2048 fine-tuning: rounds

Round 1 (running 16 Oct): dataset `data/ft2048` (priority-reader labels), Kaggle kernels
`codeyatri-laya-2048-finetune` (12k rows, 2 epochs) and `codeyatri-laya-2048-finetune-full` (all rows, 4 epochs),
plus a laptop head-only run to `data/ft2048/ckpt_head`.

Evaluate any checkpoint the same way, simulator first:
```
.venv\Scripts\python scripts\probe_2048.py --states 150 --styles v3 --model <checkpoint dir>
.venv\Scripts\python scripts\eval_arena.py --game 2048 --games 10 --style v3 --model <checkpoint dir> --runs runs_sim_ckpt
```
Compare against zero-shot (agreement 0.51, no 512 tile) and the perfect reader (512 in 75% of games).

Round 2 (after the first checkpoint): the model now reaches boards the reader never saw, so label those too.
```
.venv\Scripts\python scripts\eval_arena.py --game 2048 --games 40 --style v3 --model <ckpt> --runs runs_sim_r2
.venv\Scripts\python scripts\make_2048_dataset.py --out data\ft2048_r2 --laya-logs "runs_sim_r2/*/2048/*[!s].jsonl"
```
Then upload `data\ft2048_r2` as a new dataset version and rerun the full kernel on it.

Rules check before any counted run with a fine-tuned checkpoint: the organisers must have said yes (mentor question 4).

## 7. Stage 3 (Doom-style): zero-shot, no training

The game is revealed only after the 2048 unlock, so there is no time to train. We use the method that
took Snake from 0 foods to 19 wins of 20 without training: one yes/no question per direction, facts
only, no direction word in the question, a priorities line, legal moves only, base `english` checkpoint.

Prepared in advance: `src/laya_agent/arena/grid_facts.py` (generic per-direction facts for any grid
game: wall, hazard, enemy adjacency, closer/farther to the target, dead-end pocket). On reveal:
1. Create one session, save the raw state, map its fields onto `GridView` (player, walls, hazards, enemies, targets).
2. Write the priorities line (stay alive, avoid enemies, reach the target) and the state text.
3. Write the mapping as JSON (see the docstring of `src/laya_agent/arena/grid_game.py`: player, grid codes
   or cell lists for walls, hazards, enemies and targets, priorities, points field) and check the facts on the
   saved state: `python -c "from laya_agent.arena.grid_game import *; ..."`. Every direction's fact must be
   true and contain no verdict. No code change is needed; the runner loads it with `--grid-spec doom.json --game doom`.
4. Play one session with the viewer visible; iterate on wording from the logs, as with Snake E3.
Budget: 30 to 60 minutes. The viewer and the log format need no change (same four actions).
If the state is pixels rather than structured fields, ask the organisers for a structured state; Laya reads text only.

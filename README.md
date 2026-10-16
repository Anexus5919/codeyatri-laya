# CodeYatri: teaching Laya to play

Team **CodeYatri** for Genesis 2.0, PS 02 "Beat the Bot: Teach Laya to Play": Adarsh Singh (lead), Piyush Shukla, Mayuresh Sarkale, Vidushi Singh.

A decision layer that plays the hosted games on [topgameai.com/arena](https://topgameai.com/arena) through their agent API. **Every move comes from a visible, logged call to [Laya](https://github.com/NandhaKishorM/laya)**, a small open-weight decision model. Python reads the game, writes true facts about each possible move, asks Laya one yes/no question per direction, plays Laya's highest-rated move, and logs the decision before sending it.

## Verified results (real arena sessions)

| Game | Session id | Points | Notes |
|---|---|---|---|
| Snake | `2ba7267e-def5-4fdc-aa53-0a249329eab9` | **1000** (15 of 15 foods, 127 moves) | Base Laya `english`, zero-shot, no fallback moves, log verified |
| 2048 | pending unlock | | Fine-tuned Laya, see below |

Every real session, including failed or abandoned ones, is listed in [`docs/results.md`](docs/results.md). The logs are in [`runs/`](runs/).

## How a move is made

```mermaid
flowchart LR
    A[Arena API: state] --> F[Python: one-move facts per direction]
    F --> Q[One yes/no question per legal direction]
    Q --> L[Laya, one forward pass]
    L --> P[Probabilities over up/down/left/right]
    P --> G[(Log decision, fsync)]
    G --> S[Send Laya's move] --> A
    G --> V[Live decision viewer]
```

1. **Facts, never verdicts.** For each direction Python states what the move does right now: wall or body hit, food eaten, distance to the food before and after, open space left; for 2048, whether the largest tile stays in its corner, board order, empty cells, merges. It never says which move is best, and never looks more than one move ahead.
2. **One Laya call per move.** One `noul` (yes/no) question per legal direction, answered in a single pass. The four P(true) values are normalised into the required probability block, and the highest is the move.
3. **Log before act.** The decision is written and fsynced before the move is sent. Each log line is hash-chained (`hash = sha256(prev_hash + "|" + canonical JSON)`), exactly as the participant guide specifies.
4. **Safe API handling.** A move is sent once. If a response is lost, the session is read back from the server instead of resending, so no move is ever applied twice.
5. **Fallback.** A rule-based safety move is allowed by the rules for at most 10% of moves. Our verified Snake run used none.

## What we ask Laya, and why

The problem statement says teams using the same model will score very differently. These measured findings are why ours works ([`docs/experiments.md`](docs/experiments.md) has the full log):

| Finding | Before | After |
|---|---|---|
| One yes/no per move instead of one multiple-choice question (grid test) | 0.61 to 0.69 | 1.00 |
| Remove the direction word from the question; Laya's prior for "right" was outweighing the facts (Snake) | 0.61 | 0.99 |
| Priorities line in every question (without it Laya picked fatal moves) | 43 fatal picks in 200 | 0 |
| Eat fact worded like the options Laya already reads well | circled the food for 300 moves | wins |
| "Moves since the last food" fact, so a deterministic model cannot repeat the same loop | 1 game stuck | 20 of 20 won in simulation |

## 2048: fine-tuned Laya

Zero-shot Laya never reached a 512 tile in 14 simulated games, even with good facts. A program that follows the stated priorities exactly from the same facts reaches 512 in 75% of games, which showed the facts carry the signal and Laya's reading was the bottleneck. The organisers confirmed fine-tuning Laya is allowed, so:

- **Dataset (built by us, kept private on Kaggle):** 2048 boards from our local simulator, the exact questions our bot asks, and true/false labels from the stated priorities applied to one-move facts. No search, no other model. Built by [`scripts/make_2048_dataset.py`](scripts/make_2048_dataset.py); round 2 adds the boards our fine-tuned Laya itself reaches.
- **Training:** Laya's official `laya-train` / `laya.train.finetune`, on a laptop RTX 3050 (decision head) and on Kaggle T4 GPUs (full model, [`notebooks/kaggle_finetune_2048.py`](notebooks/kaggle_finetune_2048.py)).
- **Result so far (simulator):** zero-shot Laya reached 512 in 0 games; the decision-head fine-tune in 7 of 24; the full-model fine-tune in **19 of 24 (79%)**, with 14 games reaching 1024 and one reaching 2048 (median 586 points on fresh seeds). Held-out yes/no agreement went from 0.49 to 0.93.

The move is still always Laya's own answer; only the checkpoint changes.

## Run it

Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
# GPU: install the CUDA build of torch from pytorch.org into the same environment

# live decision viewer (keep it visible while the bot plays)
python -m laya_agent.viewer.arena_web runs --port 8770     # http://127.0.0.1:8770

# one real session on the arena, agent name CodeYatri
python -m laya_agent.arena.runner --game snake
python -m laya_agent.arena.runner --game 2048 --style v3 --model <fine-tuned checkpoint dir>

# local simulators (test only, never reported as results)
python -m laya_agent.arena.runner --game snake --sim --seed 1
python scripts/eval_arena.py --game snake --games 10

pytest -q
```

Each session writes three files to `runs/<game>/`: `<session_id>.jsonl` (the submission log, hash-chained), `<session_id>.events.jsonl` (facts and raw P(true) for the viewer) and `<session_id>.final.json` (the game's final response, saved the moment it ends). The runner prints a verifier report at the end: hash chain, contiguous steps, decision blocks, fallback share, and a match against the final response.

## Stage 3 (Doom-style)

Revealed only after 2048, so there is no time to train. We use the zero-shot method that took Snake to 1000: [`grid_facts.py`](src/laya_agent/arena/grid_facts.py) computes the same per-direction facts for any grid game, and [`grid_game.py`](src/laya_agent/arena/grid_game.py) registers a new game from a short JSON field mapping (`--grid-spec`). Rehearsed on an unseen practice game: 5 of 5 wins after one mapping fix.

## Repository layout

```
src/laya_agent/
  arena/      client.py (arena API), games.py (Snake and 2048 facts), grid_facts.py, grid_game.py,
              decider.py (the only move chooser), spec_log.py (submission log + verifier),
              runner.py (one session), sims.py (local test simulators)
  viewer/     arena_web.py + arena_static/ (live decision viewer)
  decision/, game/, telemetry/, loop.py   earlier generic engine (pre-hackathon prototype)
scripts/      eval_arena.py, probe_snake.py, probe_2048.py, make_2048_dataset.py
notebooks/    Kaggle fine-tuning script, Colab runner
tests/        unit and integration tests (a fake Laya lives only here)
docs/         experiments.md, writeup.md, results.md, decisions.md, research.md, hackathon-day.md, evidence/
runs/         real arena session logs
```

## Write-up

[`docs/writeup.md`](docs/writeup.md): what we asked Laya, why, what failed, and what we changed.

## Attribution

Laya source, docs and Python package: [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) (Apache-2.0). Model checkpoints: [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya) on Hugging Face. Games: [TopGameAI Arena](https://topgameai.com/arena).

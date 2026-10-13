# Write-up: teaching Laya to play

Filled in as we go. Results marked LOCAL FIXTURE are offline tests, not hosted runs.

## 1. Research and chosen approach

Laya is a small encoder model that scores the options we write against the state we write. It cannot search or plan, and the base checkpoints are close to chance on decisions out of the box. So the approach is: Python turns the game state into short, true facts about each legal move; Laya weighs those facts against the game's stated priorities; every answer is logged before the move is sent. Details and sources: `docs/research.md`.

## 2. What we ask Laya, and why

- One `choice` question per move, one option per legal move, labels mapped back to the exact API action.
- Option text leads with the decisive fact, because each option is cut at 48 tokens and the instructions only get the budget the options leave.
- The game's general priorities go in the instruction once. Python never marks a move as best.
- Designs tried and why: see `docs/experiments.md`.

## 3. Input and action validation

Legal moves come from the server. States are validated and refetched, never repaired. Laya's answer must map to exactly one current legal move with sane probabilities and no options lost to the token budget, otherwise the bot pauses. `laya_agent.audit` proves the trace from the log.

## 4. Baseline performance

_To fill: zero-shot design on stage 1, several runs, verified scores._

## 5. Main experiments

_To fill from `docs/experiments.md`._

## 6. Representative failures and causes

- First offline probe: the correct option received the lowest probability, and reversing the option order flipped the answer (position bias). See `docs/evidence/smoke_english_cpu.json`.

## 7. What we changed after failures

_To fill._

## 8. Verified results and session ids

_To fill from hosted runs only._

## 9. Limitations and future work

_To fill._

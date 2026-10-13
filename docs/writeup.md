# Write-up: teaching Laya to play

Filled in as we go. Results marked LOCAL FIXTURE are offline tests, not hosted runs.

## 1. Research and chosen approach

Laya is a small encoder model that scores the options we write against the state we write. It cannot search or plan, and the base checkpoints are close to chance on decisions out of the box. So the approach is: Python turns the game state into short, true facts about each legal move; Laya weighs those facts against the game's stated priorities; every answer is logged before the move is sent. Details and sources: `docs/research.md`.

## 2. What we ask Laya, and why

- We started with one `choice` question per move (one option per legal move). On 54 offline probe states it was barely above chance (0.61 to 0.69 against 0.53), confidence did not predict correctness, and reversing the option order often flipped the answer.
- We now ask **one yes/no (`noul`) question per legal move, all in the same forward pass**: the game's objective and general priorities, then "Is this a good move now?" and that move's facts. The move is the one with the highest P(true). This scored 1.000 on the same states, and 0.963 when the facts were given as bare numbers.
- Each move's description states its effect in plain words that mirror the priorities, then the number, because that widened Laya's margin between good and bad moves (mean P(good) 0.73 versus 0.575).
- Python never marks a move as best and never removes a legal move by preference. Designs and numbers: `docs/experiments.md`.

## 3. Input and action validation

Legal moves come from the server. States are validated and refetched, never repaired. Laya's answer must map to exactly one current legal move with sane probabilities and no options lost to the token budget, otherwise the bot pauses. `laya_agent.audit` proves the trace from the log.

## 4. Baseline performance

_To fill: zero-shot design on stage 1, several runs, verified scores._

## 5. Main experiments

_To fill from `docs/experiments.md`._

## 6. Representative failures and causes

- First offline probe: the correct option received the lowest probability, and reversing the option order flipped the answer (position bias). See `docs/evidence/smoke_english_cpu.json`.
- Averaging over all option orders fixed the flipping but not the accuracy: the problem was reading, not position.
- With numbers only, two of 54 states went wrong because the margins between moves were small (about 0.05). Absolute P(true) values overlap across states, so they can rank moves within a turn but cannot be used as a fixed threshold.
- CPU latency on a shared laptop swung between about 1 s and 4.7 s per decision with four questions. Real-time stages need a GPU.

## 7. What we changed after failures

- `choice` with facts (near chance) changed to one `noul` question per move (1.000 offline). Evidence: E1.
- Numeric-only facts changed to effect words plus numbers (wider margins). Evidence: E2.
- Confidence gating dropped in favour of within-turn ranking. Evidence: E1, E2.

## 8. Verified results and session ids

_To fill from hosted runs only._

## 9. Limitations and future work

_To fill._

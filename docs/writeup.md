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

Simulator results with real Laya on an RTX 3050 (16 Oct). Hosted results will replace these once real sessions are played.

- **Snake, zero-shot:** first wording ("Is moving right a good move now?") ate 0 foods in 300 moves. After removing the direction word from the question, 19 wins of 20 games (1000 points each); the one loss became a win after adding a "moves since the last food" fact. 70 to 110 ms per decision.
- **2048, zero-shot:** best tile 256 at most across 14 games, no 512. On 150 probe positions Laya agreed with the stated priorities 39% to 51% of the time, close to chance.

## 5. Main experiments

E1 and E2 (coin grid): one yes/no per move beats a single multiple-choice question (1.00 vs about 0.65).
E3 (Snake): naming the direction in the question let Laya's prior about the word outweigh the facts (0.61); removing it gave 0.91, and rewording the eat fact to mirror the other options gave 0.99.
E4 (Snake, full games): 19 of 20 wins; a changing fact fixes circling.
E5 (2048): zero-shot near chance, while a reader of the same facts reaches 512 in 75% of games. E7 to E9: fine-tuning Laya on labels from the stated priorities (allowed by the organisers): decision head only 7 of 24 games at 512, full model 19 of 24, with 14 at 1024 and one 2048. Details in `docs/experiments.md`.

## 6. Representative failures and causes

- First offline probe: the correct option received the lowest probability, and reversing the option order flipped the answer (position bias). See `docs/evidence/smoke_english_cpu.json`.
- Averaging over all option orders fixed the flipping but not the accuracy: the problem was reading, not position.
- With numbers only, two of 54 states went wrong because the margins between moves were small (about 0.05). Absolute P(true) values overlap across states, so they can rank moves within a turn but cannot be used as a fixed threshold.
- CPU latency on a shared laptop swung between about 1 s and 4.7 s per decision with four questions. Real-time stages need a GPU.
- Snake: with the direction word in the question, Laya chose "right: farther from the food" over "down: closer" and circled for 300 moves. The word, not the fact, was driving the answer.
- Snake: with identical facts repeated, the snake circled near the food; a changing true fact (moves since the last food) broke the loop.
- 2048: Laya cannot weigh three priorities at once zero-shot. Short clauses kept the corner better (1 corner loss vs 9) but ranked the rest worse.

## 7. What we changed after failures

- `choice` with facts (near chance) changed to one `noul` question per move (1.000 offline). Evidence: E1.
- Numeric-only facts changed to effect words plus numbers (wider margins). Evidence: E2.
- Confidence gating dropped in favour of within-turn ranking. Evidence: E1, E2.
- Direction word removed from Snake questions; eat fact reworded; moves-since-food fact added. Evidence: E3, E4.
- 2048 facts rewritten against a fixed corner with an order measure; fine-tuning dataset built from the stated priorities. Evidence: E5.

## 8. Verified results and session ids

- **Snake, 16 Oct 2026 12:39 IST, session `2ba7267e-def5-4fdc-aa53-0a249329eab9`: 1000 points** (15 of 15 foods, 127 moves, won). Base `english` checkpoint, zero-shot, template `noul_nodir`, no fallback moves. The log verifies against the arena's final response (hash chain intact, 127 contiguous steps). Public leaderboard: #6, level with the top large-model entries on points.
- 2048 and stage 3: pending the unlock confirmation. Full table in `docs/results.md`.

## 9. Limitations and future work

_To fill._

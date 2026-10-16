# Experiment log

One principal change per experiment. LOCAL FIXTURE results are offline tests of how Laya reads our inputs; they are never hosted results. Hosted results always cite run ids and session ids.

Template:

```
## E<n>: <title>
- Date, environment (LOCAL FIXTURE / HOSTED), checkpoint, device
- Hypothesis
- Baseline configuration
- Variable changed
- Runs / probe set
- Results (table)
- Failure examples
- Interpretation
- Decision: keep / revert
```

## E0: Smoke test of the documented API

- 2026-10-13, LOCAL, `english` checkpoint (revision 7b928d8), CPU, laya 0.4.6.
- Hypothesis: the documented `Router.predict` call works and returns the documented shape.
- Result: works; shape matches the installed source; deterministic for identical input; warm p50 395 ms on CPU.
- Failure found: asked for the fastest route to the coin, Laya ranked the option literally described as "closer to the coin" last (0.148) and chose "farther from the coin" (0.417). Reversing the option order flipped the answer.
- Interpretation: zero-shot Laya does not reliably read our option facts, and option position matters. Question design has to be measured, not assumed.
- Evidence: `docs/evidence/smoke_english_cpu.json`.

## E1: Which question design lets base Laya read move facts?

- 2026-10-13, LOCAL FIXTURE, `english` checkpoint, CPU, laya 0.4.6.
- Probe set: initial states of coin-grid seeds 0 to 59, keeping the 54 where some but not all legal moves get closer to the coin. Each state is asked twice: options in normal order and reversed.
- Scoring only: a move is "good" if the fixture's BFS distance to the coin drops. BFS never chooses a move.
- Hypothesis: adding factual descriptions and the game's priorities lifts accuracy well above chance; averaging over option orders removes position bias.
- Variable: question design (wording, labels, question type, aggregation). Everything else fixed.

| design | accuracy | reversed order | order agreement | mean P(good) | acc, high conf half | acc, low conf half | p50 ms (CPU) |
|---|---|---|---|---|---|---|---|
| bare_v1 (names only) | 0.667 | 0.611 | 0.741 | 0.561 | 0.630 | 0.704 | 778 |
| facts_v1 | 0.611 | 0.630 | 0.722 | 0.578 | 0.630 | 0.593 | 381 |
| goal_v1 | 0.667 | 0.648 | 0.833 | 0.594 | 0.593 | 0.741 | 465 |
| opaque_v1 | 0.685 | 0.778 | 0.648 | 0.610 | 0.667 | 0.704 | 457 |
| rot_v1 (mean over cyclic orders) | 0.648 | 0.630 | 0.815 | 0.588 | 0.519 | 0.778 | 1241 |
| noul_each_v1 (one yes/no per move) | **1.000** | **1.000** | **1.000** | 0.730 | 1.000 | 1.000 | 1105 |

Chance (uniform over legal moves): 0.526.

- Interpretation:
  - Every single `choice` design is close to chance even when the option text literally says "closer to the coin". The choice head does not compare our descriptions well zero-shot.
  - Confidence on `choice` answers did not predict correctness (the high-confidence half was no better, sometimes worse). Zero-shot confidence cannot be used for gating.
  - Order averaging raised order agreement but not accuracy: it removes position noise, not the reading problem.
  - Asking one yes/no question per legal move, in the same forward pass, was correct on all 54 states in both orders. Laya is much better at judging one stated fact against the stated priorities than at comparing options against each other.
- Caveat: the descriptions use the same words as the priorities ("closer", "farther"). E2 checks whether Laya still reads plain numbers.
- Decision: keep `noul_each_v1` as the starting design. Cost: one question per legal move (32 max per call) and higher CPU latency.
- Evidence: `docs/evidence/design_eval_english_cpu.json`.

## E2: Does Laya read numbers, or only matching words?

- 2026-10-13, LOCAL FIXTURE, `english`, CPU. Same 54 probe states as E1.
- Hypothesis: if E1's 1.000 came from word matching ("closer" in both priorities and option), numeric-only descriptions will drop `noul_each_v1` towards chance.
- Variable: description style. Words ("move up: closer to the coin (3 to 2 steps)") versus numbers only ("move up: coin distance 3 to 2 steps").

| design | words: accuracy | numbers: accuracy | numbers: order agreement | numbers: mean P(good) |
|---|---|---|---|---|
| goal_v1 | 0.667 | 0.667 | 0.833 | 0.596 |
| opaque_v1 | 0.685 | 0.667 | 0.759 | 0.608 |
| noul_each_v1 | 1.000 | **0.963** | 1.000 | 0.575 (words: 0.730) |

- Per-move P(true) with numbers: good moves median 0.605 (range 0.471 to 0.729), bad moves median 0.479 (range 0.345 to 0.667). Best good minus best bad, per state: median +0.118, worst -0.116.
- Failures: seed 13 (picked `left` 0.612 over good `right` 0.565) and seed 25 (picked `left` 0.667 over good `up`/`down` near 0.55).
- Interpretation:
  - Laya does read the numbers: 0.963 without any matching words, still far above chance (0.526) and above every `choice` design.
  - Stating the effect in words that mirror the priorities widens the margin (mean P(good) 0.73 versus 0.575) and removed both failures.
  - P(true) is only meaningful **within** a state. Values overlap across states, so a fixed threshold would be wrong. Reading probabilities here means ranking, not gating.
- Decision: default design `noul_each_v1`. Adapter rule for hackathon day: each move's description states its effect in plain words that mirror the priorities, then the number.
- Evidence: `docs/evidence/design_eval_english_cpu_numeric.json`.

## E3: Snake question wording (real game rules, LOCAL SIMULATOR positions)

- 2026-10-16, LOCAL SIMULATOR of the topgameai Snake arena (12x12, start length 3, same JSON as the real API), `english` checkpoint on the RTX 3050 GPU (about 70 to 110 ms per decision with 3 questions).
- First full simulated game (old wording "Is moving right a good move now?"): survived all 300 moves but ate **0 foods**. Logs show Laya scoring "right" about 0.1 higher than other directions with identical facts, even choosing "right: farther from the food" over "down: closer", and "down: farther" over "left: eats the food".
- Probe set: 200 positions from simulated games where some but not all safe moves are good (good = safe and eats, else safe, not trapped and closest to the food). Chance 0.46.

| wording | good-move rate | fatal picks | missed eats |
|---|---|---|---|
| noul_v1: priorities + "Is moving {direction} a good move now?" + fact | 0.61 | 0 | 8 |
| noul_nodir: priorities + "Is this a good move now? This move: {fact without direction}" | 0.91 | 0 | 17 |
| noul_nodir_short: same without priorities | 0.655 | 43 | 10 |
| noul_nodir + eat fact reworded to "safe, eats the food now (+60 points), open space N cells" | **0.99** | 0 | 1 |

- Interpretation: naming the direction lets Laya's prior about the word ("right", "up") outweigh the facts. Removing it makes Laya judge the facts. The priorities line is essential (without it Laya picked fatal moves 43 times). The eat fact lost to "safe, closer..." until it also said "safe" and stated the open space, mirroring the other options.
- Decision: default template `noul_nodir`, eat fact reworded. Evidence: `docs/evidence/probe_snake_templates.json`, `docs/evidence/probe_snake_nodir_eatfix.json`.

## E4: Snake end to end (LOCAL SIMULATOR, real Laya on GPU)

- 2026-10-16. Template `noul_nodir`, legal moves only, state text now includes "Moves since the last food: N" (a true, changing fact that stops identical questions repeating when the snake circles).
- Seeds 100 to 109: 9 wins of 10 (1000 points each), one game stuck circling at 3 foods (180 points). After adding the moves-since-food fact, that seed wins in 103 moves. Seeds 200 to 209: **10 wins of 10**, 102 to 144 moves each, no fallbacks, every log verifies.
- Decision latency on the RTX 3050: about 70 to 110 ms per move (3 questions).
- Caveat: simulator only. The real arena may differ in collision timing (the facts treat the tail cell as solid, the safe side) and food placement.
- Evidence: `docs/evidence/eval_snake_nodir_sim.json`, `docs/evidence/eval_snake_nodir_sincefood_sim.json`.

## E5: 2048 zero-shot is near chance; a reader of our own facts is not

- 2026-10-16, LOCAL SIMULATOR, `english` on GPU, template `noul_nodir`.
- Full games (6, facts v2): best tiles 64 to 256, median points 144, no 512. Full games (8, facts v3): best tiles 32 to 256, median points 0.
- Probe (150 positions where legal moves differ under the priorities; label = corner first, then board order, then empty cells):

| fact style | agreement with the priorities | picks that lose the corner |
|---|---|---|
| v3 (corner, order trend with counts, empty trend, merges named) | 0.513 | 9 |
| v3s (same, short clauses) | 0.473 | 1 |
| v3n (numbers only) | 0.420 | 26 |
| v3c (corner clause only) | 0.387 | 0 |

- Offline ceiling check (no Laya): a program that reads the v3 facts and applies the stated priorities exactly reaches a 512 tile in **75%** of 60 games (1024 in 42%). So the facts carry enough to pass the stage-2 gate; zero-shot Laya cannot weigh three priorities at once.
- Decision: prepare fine-tuning on priority-reader labels (dataset `data/ft2048`: 20,311 train rows, 5,710 held-out rows from different games, 72,515 questions, 36% true). Whether a fine-tuned Laya may be used in counted runs is a question for the organisers.
- Evidence: `docs/evidence/eval_2048_nodir_v2_sim.json`, `docs/evidence/eval_2048_nodir_v3_sim.json`, `docs/evidence/probe_2048_styles.json`.

## E6: Stage-3 rehearsal: an unseen grid game, zero-shot, no code change

- 2026-10-16, LOCAL SIMULATOR `GridSim` (a dungeon: walls, 4 monsters, 3 pits, one exit; field names the bot had never seen: `tiles`, `hero{col,row}`, `monsters`, `exit`), real Laya `english` on GPU, template `noul_nodir`, generic facts from `grid_facts.py` through a JSON mapping (`fixtures/dungeon_spec.json`).
- First attempt died at step 9: Laya chose "closer to the exit, next to 1 enemy" and stepped onto the monster. The mapping had declared monsters as "threats" (dangerous to stand beside) but not as "hazards" (fatal to enter). One line in the JSON fixed it.
- After the fix: seeds 4 to 8, **5 wins of 5**, 1 to 41 moves, no fallbacks, every log verified. Points 795 to 995 (1000 minus 5 per step).
- Lessons for the day: (1) read one real state and map every cell code to wall, hazard, enemy or target before playing; (2) a death in the log points straight at the missing fact; (3) the method that worked for Snake transfers without training.
- Evidence: simulator logs kept locally (simulator runs are not committed); the mapping is `fixtures/dungeon_spec.json` and the simulator is `GridSim` in `src/laya_agent/arena/sims.py`.

## E7: First fine-tuned checkpoint on 2048 (head only, epoch 1 of 2, trained on the laptop)

- 2026-10-16. `laya-train --freeze-encoder --loss soft-ce` on `data/ft2048/train.jsonl` (72,515 yes/no questions), RTX 3050, epoch-1 checkpoint `data/ft2048/ckpt_head/checkpoint_latest`. Same template `noul_nodir` and facts v3 as zero-shot.
- Probe (same 150 positions as E5): agreement with the priorities **0.92** (zero-shot 0.51), corner-losing picks **0** (zero-shot 9).
- Full simulator games (same seeds 100 to 107 as the zero-shot v3 run):

| | zero-shot (E5) | fine-tuned head, epoch 1 |
|---|---|---|
| reached 512 | 0 of 8 | **3 of 8** |
| best tiles | 32, 32, 64, 64, 64, 128, 256, 256 | 128, 256, 256, 256, 256, 512, 512, 512 |
| median points | 0 | 289.5 |
| fallbacks | 0 | 0 |

- Interpretation: the facts carried the signal (E5's ceiling check) and only the decision head needed teaching to weigh them. The perfect reader's 75% at 512 is the next target; the full-model Kaggle run trains the encoder too.
- Every move is still a logged Laya call; only the checkpoint changed. Using a fine-tuned checkpoint in counted runs awaits the organisers' answer.
- Evidence: `docs/evidence/probe_2048_ckpt_head_epoch1.json`, `docs/evidence/eval_2048_ckpt_head_e1_sim.json`.

## E8: Final laptop checkpoint and a comparison mistake

- 2026-10-16. Final head-only checkpoint (2 epochs): held-out yes/no agreement 0.489 to **0.830**, calibration error (ECE) 0.084 to **0.015**. Probe agreement 0.94, corner-losing picks 0.
- Full simulator games with the final checkpoint: seeds 100 to 107, 1 of 8 reached 512; seeds 300 to 315, 6 of 16 reached 512 (one 1024, 583 points). Total **7 of 24 (29%)**, median points 289.
- Mistake: a planned epoch-1 vs final comparison was invalid (its duplicate result file was removed; `docs/evidence/eval_2048_cmp_final_seeds300.json` is the valid one). `laya-train` rewrites `checkpoint_latest/` after every epoch, so by the time of the comparison it already held epoch 2; both arms tested the same weights (identical results exposed it). The earlier epoch-1 result (3 of 8 on seeds 100 to 107) was measured before the overwrite and stands, but cannot be rerun. Rule since then: copy a checkpoint to a frozen folder before testing it.
- Teacher check (offline, no Laya, 80 games): the current priority reader (corner, then order, then empty) reaches 512 in 75% and 1024 in 40%. Weighted one-move variants tied at 512 at best (81%) and lost at 1024 (24%). The teacher stays; the gap to close is imitation (29% vs 75%).
- Next: round 2. Play 40 games with the frozen final checkpoint, label the boards it reaches with the same teacher, retrain (full model on Kaggle).

## E9: Full-model fine-tune on Kaggle (12k rows, 2 epochs)

- 2026-10-16. Kaggle kernel `codeyatri-laya-2048-finetune` (2x T4): `laya.train.finetune` on the first 12,000 rows of `data/ft2048/train.jsonl` (42,451 questions), soft cross-entropy, 2 epochs, `max_len` 256, encoder and head both trained. Frozen copy: `data/ft2048/ckpt_kaggle_bounded_frozen`.
- Held-out (20,439 questions): agreement 0.489 to **0.926**, ECE 0.084 to 0.030. Probe (150 positions): **0.987**, corner-losing picks 0.
- Simulator games, same seeds as E7 and E8:

| checkpoint | seeds 100 to 107 | seeds 300 to 315 | total reaching 512 | 1024 | 2048 |
|---|---|---|---|---|---|
| zero-shot (E5) | 0 of 8 | not run | 0 of 8 | 0 | 0 |
| laptop head only (E8) | 1 of 8 | 6 of 16 | 7 of 24 | 1 | 0 |
| **Kaggle full model** | 4 of 8 | **15 of 16** | **19 of 24 (79%)** | 14 | 1 (741 points) |

- Median points on seeds 300 to 315: **586** (mean 549). No fallback moves; every log verifies.
- Interpretation: training the encoder, not just the decision head, is what lets Laya read the fact text the way the priorities intend. The fine-tuned Laya matches the perfect reader it was trained on (75% at 512) and slightly exceeds it on these seeds, likely because its soft preferences break ties better than the reader's fixed order.
- Decision: this checkpoint plays the real 2048 runs unless a later one (round 1 full data, round 2) beats it on the same seeds.
- Evidence: `docs/evidence/probe_2048_kaggle_bounded.json`, `docs/evidence/eval_2048_kaggle_bounded_seeds100.json`, `docs/evidence/eval_2048_kaggle_bounded_seeds300.json`.

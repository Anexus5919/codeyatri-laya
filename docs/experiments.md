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

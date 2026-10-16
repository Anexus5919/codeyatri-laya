# Decisions and organiser rulings

| Date (IST) | Question | Answer | Source | Effect |
|---|---|---|---|---|
| 2026-10-16 ~13:30 | May we fine-tune Laya? | Yes, fully: fine-tuning and training Laya are allowed. Still banned: any other model, search algorithms, and browser extensions or other external tools choosing or playing moves. | Hackathon coordinators, asked in person by the team lead | 2048 may use our fine-tuned Laya checkpoint in counted runs. Training labels must stay rule-based readings of one-move facts (no search, no other model). |
| 2026-10-16 ~20:00 | What is stage 3? | The real Doom, played in an open-source engine on our own machine, with Laya making every decision (move, turn, aim, shoot, open doors). Fine-tuning and practice are allowed; scoring rewards a good result; latency matters because the game runs in real time. | Hackathon organisers, asked in person by the team lead | Built `laya_agent.doom` on ViZDoom with the free Freedoom game data, real-time mode, and a demo recording of every episode as proof. |

## Standing design rules (from the rules and the ruling above)

- Every move is the argmax of a logged Laya call. Python computes one-move facts and checks legality; it never chooses.
- Training labels come from the priorities we state in the question, applied to one-move facts. No search, no lookahead, no other model, at training time or at play time.
- One checkpoint per game: Snake on base `english` (1000 points zero-shot), 2048 on its fine-tuned checkpoint, Doom on its own fine-tuned checkpoint (trained on Doom facts only).

## Doom (stage 3) design rules

- Engine: ViZDoom (GPL, built on ZDoom) with Freedoom data (BSD). No paid game files are used or needed.
- Laya reads the engine's own state as text. No vision model: the screen is shown to people, never to a model.
- One Laya call per decision, one yes/no question per offered action (shoot, fine and coarse turns, move, strafe, use). The action played is the highest P(yes). There is no rule-based override in Doom, so every logged decision has source `laya`.
- Facts are one-step readings: a straight line from the player to the first wall, where an enemy sits relative to the crosshair after one turn, whether a strafe leaves a fireball's path. Memory is limited to what the player has seen and done (visited ground, the last action, a door already pressed). Nothing searches for a path or plans several actions ahead.
- Training labels are a fixed priority reading of the same facts (shoot what is in the crosshair, turn toward the nearest enemy, dodge, open doors, explore new ground, pick up health when hurt). The reader also plays the offline games that produce training states; it never plays a counted episode.
- Proof of play: the hash-chained log (same fields and hash rule as the arena games, with Doom's action names as probability keys) and the engine's demo recording of the episode, whose sha256 is in the final record. Replaying the recording in the engine reproduces the result.


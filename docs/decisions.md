# Decisions and organiser rulings

| Date (IST) | Question | Answer | Source | Effect |
|---|---|---|---|---|
| 2026-10-16 ~13:30 | May we fine-tune Laya? | Yes, fully: fine-tuning and training Laya are allowed. Still banned: any other model, search algorithms, and browser extensions or other external tools choosing or playing moves. | Hackathon coordinators, asked in person by the team lead | 2048 may use our fine-tuned Laya checkpoint in counted runs. Training labels must stay rule-based readings of one-move facts (no search, no other model). |

## Standing design rules (from the rules and the ruling above)

- Every move is the argmax of a logged Laya call. Python computes one-move facts and checks legality; it never chooses.
- Training labels come from the priorities we state in the question, applied to one-move facts. No search, no lookahead, no other model, at training time or at play time.
- One checkpoint per game: Snake on base `english` (1000 points zero-shot), 2048 on the fine-tuned checkpoint, stage 3 starts zero-shot.

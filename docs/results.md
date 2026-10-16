# Verified runs (real arena sessions only)

Agent name: CodeYatri. One row per real session, including failed or abandoned ones (the rules forbid hiding attempts).
Simulator games are never listed here; they live in `docs/experiments.md`.

| Date (IST) | Game | Session id | Points | Steps | Won | Fallback share | Log verified | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:52 | snake | ce20b214-7853-4d6b-87e4-eef4a638bf51 | 0 | 0 | no | 0% | n/a | Format probe only: session created to read the real state shape, no move sent |
| 2026-10-16 12:39 | snake | 2ba7267e-def5-4fdc-aa53-0a249329eab9 | **1000** | 127 | yes | 0% | yes | First real run. 15/15 foods, base `english`, template `noul_nodir`, GPU shared with training (decide 170 to 350 ms, API 0.6 to 3 s) |
| 2026-10-16 15:40 | snake | 3f7271f0-1bea-4767-98d6-d391b78d8360 | 0 | 0 | no | 0% | n/a | Abandoned before the first move: stopped by hand because the laptop was overloaded (GPU shared with training). No move was sent |
| 2026-10-16 15:50 | snake | c286e971-3fd1-4b3b-b310-e2b264db8338 | **1000** | 147 | yes | 0% | yes | Second real win. 15/15 foods, base `english`, all 147 moves decided by Laya. Server record matches the log (`python -m laya_agent.arena.verify c286e971`) |
| 2026-10-16 16:30 | 2048 | f7ee009c-39d8-4697-ad6b-bb8b41453c01 | 289 (arena score 735) | 294 | no | 0% | yes | First real 2048 run, fine-tuned checkpoint `ckpt_kaggle_bounded_frozen`. Best tile 256. Lost the bottom-left corner at step 169 on a 0.093 vs 0.092 call and did not recover at step 170. Points by the guide formula; the arena's own score is 735 |
| 2026-10-16 17:24 | snake | 5e8400b5-b56b-4dc7-8d5d-b12e8a146567 | **1000** | 130 | yes | 0% | yes | Third real win. 15/15 foods, base `english`, all 130 moves by Laya, server record matches |
| 2026-10-16 17:36 | 2048 | df7287a4-1132-46f9-bc06-6b3db9a9a3fa | open (512 tile reached) | 318 | open | 0% | not yet (unfinished) | Checkpoint `ckpt_kaggle_full_frozen`. At step 319 the move request failed in transit (server still shows 318 steps) and the runner exited without waiting. Game still open on the arena; to be finished with `--resume` |

## Unlocks

- 2048: open since the Snake gate was met (1000 >= 600, session 2ba7267e-def5-4fdc-aa53-0a249329eab9); the arena does not lock games and no confirmation is needed.
- Doom-style: not yet requested.

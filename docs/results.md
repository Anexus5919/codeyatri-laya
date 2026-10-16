# Verified runs (real arena sessions only)

Agent name: CodeYatri. One row per real session, including failed or abandoned ones (the rules forbid hiding attempts).
Simulator games are never listed here; they live in `docs/experiments.md`.

| Date (IST) | Game | Session id | Points | Steps | Won | Fallback share | Log verified | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:52 | snake | ce20b214-7853-4d6b-87e4-eef4a638bf51 | 0 | 0 | no | 0% | n/a | Format probe only: session created to read the real state shape, no move sent |
| 2026-10-16 12:39 | snake | 2ba7267e-def5-4fdc-aa53-0a249329eab9 | **1000** | 127 | yes | 0% | yes | First real run. 15/15 foods, base `english`, template `noul_nodir`, GPU shared with training (decide 170 to 350 ms, API 0.6 to 3 s) |
| 2026-10-16 15:40 | snake | 3f7271f0-1bea-4767-98d6-d391b78d8360 | 0 | 0 | no | 0% | n/a | Abandoned before the first move: stopped by hand because the laptop was overloaded (GPU shared with training). No move was sent |
| 2026-10-16 15:50 | snake | c286e971-3fd1-4b3b-b310-e2b264db8338 | **1000** | 147 | yes | 0% | yes | Second real win. 15/15 foods, base `english`, all 147 moves decided by Laya. Server record matches the log (`python -m laya_agent.arena.verify c286e971`) |

## Unlocks

- 2048: Snake gate met (1000 >= 600) by session 2ba7267e-def5-4fdc-aa53-0a249329eab9; unlock confirmation to be requested from the organisers.
- Doom-style: not yet requested.

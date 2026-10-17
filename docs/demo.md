# Demo commands (judging, 17 Oct 2026)

Every command runs from the repo folder in PowerShell, after:

```powershell
cd C:\Users\ANEXUS\Desktop\laya-game-agent
.venv\Scripts\activate
```

## 1. Dashboard (start first, keep it visible)

```powershell
python -m laya_agent.viewer.arena_web runs --port 8770 --sim-roots "runs_sim*"
```
Open http://127.0.0.1:8770. Header: Snake | 2048 | Doom, then Arena (real) / Simulator (test) (for Doom: Real runs / Test runs).

## 2. Snake (stage 1, base Laya, no training)

```powershell
# practice on the local simulator (no public record)
python -m laya_agent.arena.runner --game snake --sim
# real arena session (permanent public record, agent CodeYatri)
python -m laya_agent.arena.runner --game snake
```

## 3. 2048 (stage 2, fine-tuned Laya)

```powershell
# practice on the local simulator
python -m laya_agent.arena.runner --game 2048 --sim --model data\ft2048\ckpt_kaggle_full_frozen
# real arena session
python -m laya_agent.arena.runner --game 2048 --model data\ft2048\ckpt_kaggle_full_frozen
# if a real session stops part way (network), continue the same session and log
python -m laya_agent.arena.runner --game 2048 --model data\ft2048\ckpt_kaggle_full_frozen --resume <session_id>
```

## 4. Doom (stage 3, fine-tuned Laya, our own engine)

```powershell
# judged run: game window, real time, screens for the dashboard (Doom > Real runs)
python -m laya_agent.doom.runner --scenario freedoom1:E1M1 --model data\ftdoom\ckpt_quick_frozen --frames --visible --realtime --minutes 3
# test run (Doom > Test runs)
python -m laya_agent.doom.runner --scenario freedoom1:E1M1 --model data\ftdoom\ckpt_quick_frozen --runs runs_sim_doom --frames --visible --realtime --minutes 3
# combat showcase (monsters keep coming: aim and shoot)
python -m laya_agent.doom.runner --scenario defend_the_line --model data\ftdoom\ckpt_quick_frozen --runs runs_sim_doom --frames --visible --realtime --minutes 2
```
Other levels: `freedoom1:E1M2` to `E1M9`, `freedoom2:MAP01`; scenarios `defend_the_center`, `deadly_corridor`, `deathmatch`.
On a full level where exploring matters most, `data\ftdoom\ckpt_full_frozen` explored further (E15).

## 5. Proof

```powershell
# Snake / 2048: our log against the arena server's own record
python -m laya_agent.arena.verify <session_id>
# Doom: screens for a run made without --frames, rebuilt from its demo recording
python -m laya_agent.doom.frames runs\doom\<session_id>.jsonl
```
Doom proof in the dashboard: Audit tab, then "Replay the recording in the engine".

## 6. What to click for the judges

1. Arena view: the live board or game screen, Laya's yes/no answer for every move, the chosen move in red.
2. Timeline: drag to any step; for Doom, hovering shows that step's game screen.
3. History: every logged line with the exact questions sent to Laya.
4. Audit: hash chain verified; Snake/2048 matched against the arena server; Doom replayed in the engine.
5. Board: the live public leaderboard (Snake and 2048).

## 7. If something goes wrong

- Dashboard badge says "problems" right after a code change: restart the dashboard (Ctrl+C, run it again).
- Doom feels slow: close extra Chrome tabs and other GPU work; the first Laya call is a warm-up.
- A real arena run stops on a network drop: run the same command with `--resume <session_id>`.
- Tests: `python -m pytest -q` (120 pass).

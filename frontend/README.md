# CodeYatri decision arena (dashboard)

A live dashboard for Laya arena sessions: the board in 3D, every decision with the fact Laya was given for each
direction, the full step history, timing and the hash-chain audit. It reads only what the runner logs; nothing
on screen is invented.

The production build is committed in `src/laya_agent/viewer/app_dist/` and served by the Python viewer,
so running it needs no Node:

```bash
python -m laya_agent.viewer.arena_web runs --port 8770 --sim-roots "runs_sim*"
# http://127.0.0.1:8770/         the dashboard
# http://127.0.0.1:8770/classic  the original single-file viewer
```

`--sim-roots` is optional. It adds read-only simulator folders (a glob, relative to the working directory,
scanned two levels deep such as `runs_sim_r2/noul_nodir/2048`). Without it only `runs/` is listed. Real
sessions written to `runs/<game>/` (for example `runs/2048/`) appear automatically.

If `app_dist/` is missing, `/` falls back to the classic viewer.

## Header

- **Game**: Snake, 2048, and any other game found in the logs (a stage-3 grid game, for example). Choosing a
  game opens its newest session for the current data source.
- **Data source**: Arena (real) or Simulator (test). Arena is the default. A session's source comes from the
  `env` in its `session_start` (HOSTED or LOCAL_SIM), falling back to the folder it was found in.
- **Session picker**: other sessions for that game and source, newest first.
- On the right: one environment badge (Hosted arena, or a striped Simulator run badge), status, and a
  Verified indicator from `/api/verify`. In history mode, "Viewing step N" and Back to live.

When a game has no arena session yet (2048 until the organisers confirm), the arena view says so and offers
the simulator runs for that game.

## Develop

Node 20.19+ or 22.12+ (built and tested with Node 22.22).

```bash
cd frontend
npm ci                                   # exact versions from package-lock.json

# terminal 1: the API (port 8771 is the dev default)
python -m laya_agent.viewer.arena_web runs --port 8771 --sim-roots "runs_sim*"

# terminal 2: hot-reload dev server on http://localhost:5173, /api is proxied to 8771
npm run dev                              # LAYA_API=http://127.0.0.1:9000 npm run dev for another port
```

## Build

```bash
cd frontend
npm run build      # type-checks, then writes ../src/laya_agent/viewer/app_dist/
npm run typecheck  # type-check only
```

Commit `app_dist/` after a build so the viewer works on machines without Node.

## Test live updates without a GPU

`scripts/replay_session.py` copies a recorded session into another runs folder line by line, byte for byte,
so the hash chain still verifies and the env label stays what the run wrote. It refuses to write into the
repo's `runs/` folder.

```bash
python scripts/replay_session.py runs/snake/<session_id>.jsonl C:/Temp/dash_dev/runs --pace 0.8
python scripts/replay_session.py <spec.jsonl> C:/Temp/dash_dev/runs --stop-after 30   # unfinished: Idle, then Interrupted
python -m laya_agent.viewer.arena_web C:/Temp/dash_dev/runs --port 8771
```

## Views

| Route | What it shows |
|---|---|
| `#/arena` | The board (3D for Snake and 2048, SVG for other grids), the decision for the shown step, and the timeline |
| `#/sessions` | Every session, newest first, filterable by source and game |
| `#/history` | All logged lines in a virtualised list; selecting one shows its board, decision, questions and hashes |
| `#/timing` | Per-line decide, Laya call, game API and turn times with last, mean, p95 and max |
| `#/audit` | `/api/verify` result, session metadata, fallback share against the 10% limit, outcome, chain tail |

URL parameters: `?s=<session key>` pins a session (simulator keys include their folder, for example
`runs_sim_r2/noul_nodir/2048/<id>`), `&i=<line>` opens a line, `?g=2048` and `&src=sim` pick a game and
source. `?renderer=svg` before the `#` forces the 2D board (the WebGL fallback). The rail's Motion button
switches low motion; it starts from the system's reduced-motion setting.

Keyboard: the timeline is a slider (arrows move one line, Page Up/Down ten, Home goes to the first line,
End or Escape returns to live). The history list takes arrows, Page keys, Home, End and Escape.

## What the numbers mean

- **P(yes)**: each legal direction is one yes/no question; the number is Laya's P(yes) for that move
  (`p_true` in the decision event). It is not a chance of winning.
- **Share**: the same values normalised to sum to 1, as the submission log requires.
- **Not asked**: a direction missing from `p_true` got no question (reverse, wall, no-op, or excluded after
  a rejection). It shows the logged fact, never 0.
- **Fallback**: a rule-based safety move, shown with the logged reason and Laya's own pick.
- **Live** only while the session files keep growing (written in the last 15 s) and there is no
  `session_end` or final response. Otherwise Finished, Idle (no writes for 15 s to 2 min) or Interrupted
  (no writes for over 2 min and no `session_end`).
- Facts are shown without their leading "move up: " because the row already names the direction; in the
  noul_nodir design that remainder is exactly what went into the question. The exact questions and the
  board description are under "Questions sent to Laya".

## Design rules

- Graphite base, ivory text. Red is used for the brand mark and the chosen move only. Green means verified,
  amber means a warning or a fallback. Simulator runs carry a striped steel badge and board frame.
- Snake: teal body, pale head, amber food. 2048: a cool-to-warm ramp with rising luminance (slate, blue,
  teal, green, olive, gold).
- IBM Plex Sans for text and numbers (tabular figures), IBM Plex Mono for session ids, hashes and raw
  question text. Both are bundled.

## API used

Existing: `/api/sessions`, `/api/session`, `/api/verify`. Added: `/api/history?id=&after=&limit=` (each
submission line paired with the decision event written before it, plus the newest decision without a line)
and `/api/step?id=&i=` (one full line with its event and the question per direction). Sessions carry
`key`, `source`, `origin`, `status`, `env`, `env_kind`, model, device and design. `id` accepts a key or a
plain session id (the main runs folder wins).

## Dependencies

| Package | Version | Why |
|---|---|---|
| react, react-dom | 19.3.1 | UI |
| three | 0.186.1 | WebGL scene for the arena |
| @react-three/fiber | 9.8.1 | React renderer for three (demand frame loop, events); peer range react >=19 <19.4, three >=0.156 |
| motion | 12.43.0 | One motion system (bars, decision settle, rail indicator) with a global reduced-motion switch |
| @fontsource-variable/ibm-plex-sans | 5.3.0 | Text and numbers, bundled so it works offline |
| @fontsource/ibm-plex-mono | 5.3.0 | Ids, hashes and raw question text, bundled |
| vite (dev) | 8.3.4 | Dev server and production build |
| @vitejs/plugin-react (dev) | 6.1.2 | React support for Vite 8 |
| typescript (dev) | 5.9.3 | Type-checking |
| @types/react, @types/react-dom, @types/three (dev) | 19.3.0, 19.3.0, 0.186.0 | Types |

The 3D scene is a separate chunk loaded on demand; the page is usable with the SVG board while it loads.

## Layout

```
frontend/
  index.html, vite.config.ts, tsconfig.json, package.json, package-lock.json
  public/favicon.svg
  src/
    main.tsx, App.tsx
    lib/        api, polling feed, store, routes, pure derivations, 2048 move planner, motion tokens, palette, fonts
    components/ rail and header, decision panel, timeline, SVG boards, virtual list, sparklines, stats
    arena3d/    the lazy three.js scene: Snake, 2048, camera rig, probes, axis labels
    views/      arena, sessions, history, timing, audit
    styles/     tokens.css (design tokens), app.css
```

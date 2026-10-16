# CodeYatri decision arena (dashboard)

A live dashboard for Laya arena sessions: the board in 3D, every decision with the exact facts and
questions Laya was given, the full step history, timing and the hash-chain audit. It reads only what
the runner logs; nothing on screen is invented.

The production build is committed in `src/laya_agent/viewer/app_dist/` and served by the Python viewer,
so running it needs no Node:

```bash
python -m laya_agent.viewer.arena_web runs --port 8770
# http://127.0.0.1:8770/         the dashboard
# http://127.0.0.1:8770/classic  the original single-file viewer
```

If `app_dist/` is missing, `/` falls back to the classic viewer.

## Develop

Node 20.19+ or 22.12+ (built and tested with Node 22.22).

```bash
cd frontend
npm ci                                   # exact versions from package-lock.json

# terminal 1: the API, on any runs folder (port 8771 is the dev default)
python -m laya_agent.viewer.arena_web runs --port 8771

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
so the hash chain still verifies and the env label (HOSTED or LOCAL_SIM) stays what the run wrote.
It refuses to write into the repo's `runs/` folder.

```bash
python scripts/replay_session.py runs/snake/<session_id>.jsonl C:/Temp/dash_dev/runs --pace 0.8
python scripts/replay_session.py <spec.jsonl> C:/Temp/dash_dev/runs --stop-after 30   # leaves it unfinished: IDLE, then INTERRUPTED
python -m laya_agent.viewer.arena_web C:/Temp/dash_dev/runs --port 8771
```

## Views

| Route | What it shows |
|---|---|
| `#/arena` | 3D board (Snake, 2048) or SVG board, the current decision, session vitals and the step timeline |
| `#/sessions` | Every session in the runs folder, newest first, hosted and simulator runs marked apart |
| `#/history` | All logged lines in a virtualised list; selecting one shows its board, decision, questions and hashes |
| `#/timing` | Per-line decide, Laya call, game API and turn times with last, mean, p95 and max |
| `#/audit` | `/api/verify` result, session metadata, fallback share against the 10% limit, outcome, chain tail |

Add `?s=<session id>` to pin a session and `&i=<line index>` to open a line, for example
`#/history?s=2ba7267e-def5-4fdc-aa53-0a249329eab9&i=40`.
`?renderer=svg` before the `#` forces the 2D board (the WebGL fallback); `?renderer=3d` asks for 3D.
The rail's Motion button switches low motion on and off; it starts from the system's reduced-motion setting.

Keyboard: the timeline is a slider (arrows move one line, Page Up/Down ten, Home goes to the first line,
End or Escape returns to live). The history list takes arrows, Page keys, Home, End and Escape.

## What the numbers mean

- **Laya's yes-probability**: each legal direction is one yes/no question; the big number is Laya's
  P(yes) for that move (`p_true` in the decision event). It is not a chance of winning.
- **Share across asked moves**: the same values normalised to sum to 1, as the submission log requires.
- **Not asked**: a direction missing from `p_true` got no question (reverse, wall, no-op, or excluded
  after a rejection). It is labelled with the logged kind and fact, never shown as 0%.
- **Fallback**: a rule-based safety move, shown with the logged reason and Laya's own pick.
- **LIVE** only while the session files keep growing (written in the last 15 s) and there is no
  `session_end` or final response. Otherwise FINISHED (with the logged outcome), IDLE (no writes for
  15 s to 2 min) or INTERRUPTED (no writes for over 2 min and no `session_end`).
- **Simulator** sessions (env `LOCAL_SIM`, or agent `SIM-EVAL` or `TEST*`) carry a hatched label on every
  view and show "local simulator" instead of a 0 ms game API time.
- Unknown games (stage 3) get facts, probabilities and the timeline; a board is drawn only when the
  state holds a 2D numeric grid (a field named `grid`, else the first 2D numeric field, named on screen).

## API used

Existing: `/api/sessions`, `/api/session`, `/api/verify`. Added for this app:
`/api/history?id=&after=&limit=` (each submission line paired with the decision event written before
it, plus the newest decision that has no line yet) and `/api/step?id=&i=` (one full line with its
event and the question asked per direction). Sessions and summaries also carry `status`, `env`,
`env_kind`, model, device and design.

## Dependencies

| Package | Version | Why |
|---|---|---|
| react, react-dom | 19.3.1 | UI |
| three | 0.186.1 | WebGL scene for the arena |
| @react-three/fiber | 9.8.1 | React renderer for three (demand frame loop, events); peer range react >=19 <19.4, three >=0.156 |
| motion | 12.43.0 | One motion system (gauges, decision settle, rail indicator) with a global reduced-motion switch |
| @fontsource-variable/bricolage-grotesque | 5.3.0 | UI typeface, bundled so it works offline |
| @fontsource-variable/jetbrains-mono | 5.3.0 | Numbers and log text, bundled so it works offline |
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
    lib/        api, polling feed, store, routes, pure derivations, 2048 move planner, motion tokens, palette
    components/ rail and top bar, decision panel, gauges, timeline, SVG boards, virtual list, sparklines
    arena3d/    the lazy three.js scene: Snake, 2048, camera rig, probes
    views/      arena, sessions, history, timing, audit
    styles/     tokens.css (design tokens), app.css
```

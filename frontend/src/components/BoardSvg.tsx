// SVG boards: the fallback when WebGL is unavailable, the compact board in Decision history,
// and the only renderer for games the viewer does not know (drawn from a 2D numeric field).

import { useCallback, useMemo, useRef, type PointerEvent as RPointerEvent } from "react";
import type { BoardFrame, DecisionView } from "../lib/derive";
import { DELTA, DIR_LABEL, findGrid, findMarkers, fmtP, read2048, readSnake } from "../lib/derive";
import { codeColor, PAL, tileColors } from "../lib/palette";
import type { Dir, GameState } from "../lib/types";
import { DIRS } from "../lib/types";

export type HoverFn = (text: string | null) => void;

function useCellPointer(cols: number, rows: number, onCell: (x: number, y: number) => void, onLeave: () => void) {
  const ref = useRef<SVGSVGElement>(null);
  const handler = useCallback(
    (e: RPointerEvent<SVGSVGElement>) => {
      const svg = ref.current;
      const ctm = svg?.getScreenCTM();
      if (!svg || !ctm) return;
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      const x = Math.floor(pt.x);
      const y = Math.floor(pt.y);
      if (x >= 0 && y >= 0 && x < cols && y < rows) onCell(x, y);
      else onLeave();
    },
    [cols, rows, onCell, onLeave],
  );
  return { ref, onPointerMove: handler, onPointerDown: handler, onPointerLeave: onLeave };
}

function Probe({ dir, cx, cy, decision, s = 1 }: { dir: Dir; cx: number; cy: number; decision: DecisionView; s?: number }) {
  const d = decision.dirs.find((x) => x.dir === dir);
  if (!d) return null;
  if (d.asked === false || d.pYes === null) {
    return (
      <g className="probe not-asked" aria-hidden="true">
        <path d={`M${cx - 0.16 * s} ${cy - 0.16 * s} L${cx + 0.16 * s} ${cy + 0.16 * s} M${cx + 0.16 * s} ${cy - 0.16 * s} L${cx - 0.16 * s} ${cy + 0.16 * s}`} />
      </g>
    );
  }
  const h = 0.82 * s * d.pYes;
  return (
    <g className={`probe${d.chosen ? " is-chosen" : ""}`} aria-hidden="true">
      <rect x={cx - 0.36 * s} y={cy - 0.41 * s} width={0.72 * s} height={0.82 * s} rx={0.08 * s} className="probe-frame" />
      <rect x={cx - 0.36 * s} y={cy + 0.41 * s - h} width={0.72 * s} height={h} rx={0.06 * s} className="probe-fill" />
      <text x={cx} y={cy + 0.12 * s} className="probe-text" fontSize={0.3 * s}>
        {fmtP(d.pYes, 2)}
      </text>
    </g>
  );
}

function SnakeSvg({ frame, onHover }: { frame: BoardFrame; onHover: HoverFn }) {
  const snake = readSnake(frame.state);
  const prev = readSnake(frame.from);
  const w = snake?.w ?? 1;
  const h = snake?.h ?? 1;
  const onCell = useCallback(
    (x: number, y: number) => {
      if (!snake) return;
      const idx = snake.body.findIndex((p) => p.x === x && p.y === y);
      const what = idx === 0 ? "snake head" : idx > 0 ? `snake body, segment ${idx}` : snake.food && snake.food.x === x && snake.food.y === y ? "food" : "empty cell";
      onHover(`x ${x}, y ${y}: ${what}`);
    },
    [snake, onHover],
  );
  const leave = useCallback(() => onHover(null), [onHover]);
  const ptr = useCellPointer(w, h, onCell, leave);
  if (!snake) return <p className="empty-note">This state has no snake board.</p>;
  const pts = snake.body.map((p) => `${p.x + 0.5},${p.y + 0.5}`).join(" ");
  const head = snake.body[0];
  const prevHead = prev?.body[0];
  const moved = head && prevHead && frame.action && Math.abs(head.x - prevHead.x) + Math.abs(head.y - prevHead.y) === 1;
  const dir = snake.direction ?? frame.action;
  const eye = dir ? DELTA[dir] : { x: 1, y: 0 };
  const side = { x: -eye.y, y: eye.x };
  return (
    <svg ref={ptr.ref} className="board-svg snake-svg" viewBox={`-1.1 -1.1 ${w + 2.2} ${h + 2.2}`} role="img" aria-label={`Snake board ${w} by ${h}, ${frame.caption}`} onPointerMove={ptr.onPointerMove} onPointerDown={ptr.onPointerDown} onPointerLeave={ptr.onPointerLeave}>
      <rect x={-0.25} y={-0.25} width={w + 0.5} height={h + 0.5} rx={0.35} className="slab" />
      {Array.from({ length: w * h }, (_, k) => {
        const x = k % w;
        const y = Math.floor(k / w);
        return <rect key={k} x={x + 0.05} y={y + 0.05} width={0.9} height={0.9} rx={0.12} fill={(x + y) % 2 ? PAL.cellA : PAL.cellB} />;
      })}
      {snake.food ? (
        <path className="food" d={`M${snake.food.x + 0.5} ${snake.food.y + 0.16} L${snake.food.x + 0.84} ${snake.food.y + 0.5} L${snake.food.x + 0.5} ${snake.food.y + 0.84} L${snake.food.x + 0.16} ${snake.food.y + 0.5} Z`} />
      ) : null}
      {snake.body.length > 1 ? <polyline points={pts} className="snake-body" /> : null}
      {moved && prevHead ? (
        <line key={frame.key} className="trace" x1={prevHead.x + 0.5} y1={prevHead.y + 0.5} x2={head.x + 0.5} y2={head.y + 0.5} pathLength={1} />
      ) : null}
      {head ? (
        <g className="snake-head">
          <rect x={head.x + 0.1} y={head.y + 0.1} width={0.8} height={0.8} rx={0.26} />
          <circle cx={head.x + 0.5 + eye.x * 0.18 + side.x * 0.17} cy={head.y + 0.5 + eye.y * 0.18 + side.y * 0.17} r={0.07} className="eye" />
          <circle cx={head.x + 0.5 + eye.x * 0.18 - side.x * 0.17} cy={head.y + 0.5 + eye.y * 0.18 - side.y * 0.17} r={0.07} className="eye" />
        </g>
      ) : null}
      {frame.probes && head
        ? DIRS.map((d) => <Probe key={d} dir={d} cx={head.x + 0.5 + DELTA[d].x} cy={head.y + 0.5 + DELTA[d].y} decision={frame.probes!} s={0.92} />)
        : null}
    </svg>
  );
}

function Svg2048({ frame, onHover }: { frame: BoardFrame; onHover: HoverFn }) {
  const grid = read2048(frame.state);
  const n = grid?.length ?? 4;
  const onCell = useCallback((x: number, y: number) => grid && onHover(`grid[${y}][${x}] = ${grid[y][x]}`), [grid, onHover]);
  const leave = useCallback(() => onHover(null), [onHover]);
  const ptr = useCellPointer(n, n, onCell, leave);
  if (!grid) return <p className="empty-note">This state has no 2048 grid.</p>;
  const edge: Record<Dir, [number, number]> = { up: [n / 2, -0.62], down: [n / 2, n + 0.62], left: [-0.62, n / 2], right: [n + 0.62, n / 2] };
  return (
    <svg ref={ptr.ref} className="board-svg g2048-svg" viewBox={`-1.2 -1.2 ${n + 2.4} ${n + 2.4}`} role="img" aria-label={`2048 board, ${frame.caption}`} onPointerMove={ptr.onPointerMove} onPointerDown={ptr.onPointerDown} onPointerLeave={ptr.onPointerLeave}>
      <rect x={-0.15} y={-0.15} width={n + 0.3} height={n + 0.3} rx={0.25} className="slab" />
      {grid.map((row, y) =>
        row.map((v, x) => {
          const c = tileColors(v);
          return (
            <g key={`${x}-${y}`}>
              <rect x={x + 0.06} y={y + 0.06} width={0.88} height={0.88} rx={0.1} fill={v ? c.fill : PAL.cellA} />
              {v ? (
                <text x={x + 0.5} y={y + 0.5} dy="0.35em" textAnchor="middle" fill={c.text} fontSize={v >= 1024 ? 0.26 : v >= 128 ? 0.3 : 0.36} className="tile-text">
                  {v}
                </text>
              ) : null}
            </g>
          );
        }),
      )}
      {frame.probes ? DIRS.map((d) => <Probe key={d} dir={d} cx={edge[d][0]} cy={edge[d][1]} decision={frame.probes!} s={0.95} />) : null}
      {frame.action && !frame.probes ? (
        <g className="move-arrow" aria-hidden="true" key={frame.key}>
          <text x={edge[frame.action][0]} y={edge[frame.action][1]} dy="0.35em" textAnchor="middle" fontSize={0.34}>
            {DIR_LABEL[frame.action].toUpperCase()}
          </text>
        </g>
      ) : null}
    </svg>
  );
}

function GenericSvg({ frame, onHover }: { frame: BoardFrame; onHover: HoverFn }) {
  const found = findGrid(frame.state as GameState);
  const markers = useMemo(() => findMarkers(frame.state as GameState), [frame.state]);
  const rows = found?.grid.length ?? 1;
  const cols = found?.grid[0]?.length ?? 1;
  const order = useMemo(() => {
    const set = new Set<number>();
    found?.grid.forEach((r) => r.forEach((v) => v !== 0 && set.add(v)));
    return [...set].sort((a, b) => a - b);
  }, [found]);
  const onCell = useCallback(
    (x: number, y: number) => {
      if (!found) return;
      const here = markers.filter((m) => m.x === x && m.y === y).map((m) => m.label);
      onHover(`${found.key}[${y}][${x}] = ${found.grid[y][x]}${here.length ? `; ${here.join(", ")}` : ""}`);
    },
    [found, markers, onHover],
  );
  const leave = useCallback(() => onHover(null), [onHover]);
  const ptr = useCellPointer(cols, rows, onCell, leave);
  if (!found) return <p className="empty-note">This game's state has no 2D numeric grid, so no board is drawn. Facts, probabilities and the timeline still come from the logs.</p>;
  const player = markers.find((m) => /hero|player|agent|me\b/i.test(m.key));
  return (
    <figure className="generic-board">
      <svg ref={ptr.ref} className="board-svg generic-svg" viewBox={`-1.1 -1.1 ${cols + 2.2} ${rows + 2.2}`} role="img" aria-label={`Grid from state.${found.key}, ${cols} by ${rows}`} onPointerMove={ptr.onPointerMove} onPointerDown={ptr.onPointerDown} onPointerLeave={ptr.onPointerLeave}>
        <rect x={-0.2} y={-0.2} width={cols + 0.4} height={rows + 0.4} rx={0.3} className="slab" />
        {found.grid.map((row, y) =>
          row.map((v, x) => (
            <g key={`${x}-${y}`}>
              <rect x={x + 0.05} y={y + 0.05} width={0.9} height={0.9} rx={0.12} fill={codeColor(v, order)} opacity={v === 0 ? 1 : 0.55} />
              {v !== 0 && cols * rows <= 400 ? (
                <text x={x + 0.5} y={y + 0.5} dy="0.35em" textAnchor="middle" fontSize={0.34} className="code-text">
                  {v}
                </text>
              ) : null}
            </g>
          )),
        )}
        {markers.map((m, k) => (
          <g key={`${m.label}-${k}`} className={`marker${m === player ? " is-player" : ""}`}>
            <circle cx={m.x + 0.5} cy={m.y + 0.5} r={0.3} />
            <text x={m.x + 0.5} y={m.y + 0.5} dy="0.35em" textAnchor="middle" fontSize={0.3}>
              {m.key.charAt(0).toUpperCase()}
            </text>
          </g>
        ))}
        {frame.probes && player ? DIRS.map((d) => <Probe key={d} dir={d} cx={player.x + 0.5 + DELTA[d].x} cy={player.y + 0.5 + DELTA[d].y} decision={frame.probes!} s={0.9} />) : null}
      </svg>
      <figcaption className="generic-legend">
        <span>
          Drawn from <code>state.{found.key}</code>; numbers are the logged cell codes. Letters mark position fields:
        </span>
        <span className="legend-items">
          {[...new Set(markers.map((m) => m.key))].map((k) => (
            <span key={k} className="legend-item">
              <b>{k.charAt(0).toUpperCase()}</b> {k}
            </span>
          ))}
          {order.map((c) => (
            <span key={c} className="legend-item">
              <i style={{ background: codeColor(c, order) }} /> code {c}
            </span>
          ))}
        </span>
        {frame.probes && player ? <span>Probes around <code>{player.key}</code> show Laya's yes-probability per asked direction.</span> : null}
      </figcaption>
    </figure>
  );
}

export function BoardSvg({ game, frame, onHover }: { game: string | null | undefined; frame: BoardFrame; onHover: HoverFn }) {
  if (!frame.state) return <p className="empty-note">No board state logged yet.</p>;
  if (game === "snake") return <SnakeSvg frame={frame} onHover={onHover} />;
  if (game === "2048") return <Svg2048 frame={frame} onHover={onHover} />;
  return <GenericSvg frame={frame} onHover={onHover} />;
}

import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { BoardFrame, Pt } from "../lib/derive";
import { DELTA, deepEqualState, readSnake } from "../lib/derive";
import { DUR, clamp01, easeInOutCubic, easeOutBack, easeOutCubic } from "../lib/motion";
import { PAL } from "../lib/palette";
import type { Dir } from "../lib/types";
import { AxisLabels, BOARD, CameraRig, Probes, roundedBox, std, useDisposable } from "./shared";

const SLAB_H = 0.42;
const TOP = SLAB_H / 2;
const HEAD_ROT: Record<Dir, number> = { up: 0, right: -Math.PI / 2, down: Math.PI, left: Math.PI / 2 };

interface Anim {
  from: Pt[];
  to: Pt[];
  t0: number;
  dur: number;
  traceFrom: Pt | null;
  traceTo: Pt | null;
  traceT0: number;
  foodT0: number;
}

function singleMove(a: Pt[], b: Pt[]): boolean {
  if (!a.length || !b.length) return false;
  const d = Math.abs(a[0].x - b[0].x) + Math.abs(a[0].y - b[0].y);
  return d === 1 && (b.length === a.length || b.length === a.length + 1);
}

export function SnakeScene({ frame, lowMotion, onHover }: { frame: BoardFrame; lowMotion: boolean; onHover: (t: string | null) => void }) {
  const invalidate = useThree((s) => s.invalidate);
  const snake = readSnake(frame.state);
  const w = snake?.w ?? 12;
  const h = snake?.h ?? 12;
  const cell = BOARD / Math.max(w, h);
  const toWorld = (p: Pt, out = new THREE.Vector3()) => out.set((p.x + 0.5 - w / 2) * cell, 0, (p.y + 0.5 - h / 2) * cell);

  // Static board
  const board = useDisposable(() => {
    const slabGeo = roundedBox(w * cell + 0.7, SLAB_H, h * cell + 0.7, 0.18);
    const slabMat = std(PAL.slab, { roughness: 0.85 });
    const cellGeo = roundedBox(cell * 0.9, 0.05, cell * 0.9, 0.04);
    const cellMat = std("#ffffff", { roughness: 0.9 });
    const cells = new THREE.InstancedMesh(cellGeo, cellMat, w * h);
    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const k = y * w + x;
        m.makeTranslation((x + 0.5 - w / 2) * cell, TOP + 0.02, (y + 0.5 - h / 2) * cell);
        cells.setMatrixAt(k, m);
        cells.setColorAt(k, c.set((x + y) % 2 ? PAL.cellA : PAL.cellB));
      }
    cells.receiveShadow = true;
    return {
      slabGeo, slabMat, cellGeo, cellMat, cells,
      dispose() {
        slabGeo.dispose();
        slabMat.dispose();
        cellGeo.dispose();
        cellMat.dispose();
        cells.dispose();
      },
    };
  }, [w, h, cell]);

  // Dynamic pieces, reused across frames
  const parts = useDisposable(() => {
    const segGeo = roundedBox(cell * 0.78, cell * 0.5, cell * 0.78, cell * 0.16);
    const segMat = std("#ffffff", { roughness: 0.42, metalness: 0.1 });
    const segs = new THREE.InstancedMesh(segGeo, segMat, w * h + 1);
    segs.castShadow = true;
    const linkGeo = new THREE.BoxGeometry(1, 1, 1);
    const links = new THREE.InstancedMesh(linkGeo, segMat, w * h + 1);
    links.castShadow = true;
    const headGeo = roundedBox(cell * 0.9, cell * 0.62, cell * 0.9, cell * 0.2);
    const headMat = std(PAL.head, { emissive: new THREE.Color("#3fae9f"), emissiveIntensity: 0.25, roughness: 0.35 });
    const eyeGeo = new THREE.SphereGeometry(cell * 0.075, 16, 12);
    const eyeMat = new THREE.MeshBasicMaterial({ color: PAL.eye });
    const foodGeo = new THREE.OctahedronGeometry(cell * 0.3, 0);
    const foodMat = std(PAL.food, { emissive: new THREE.Color(PAL.food), emissiveIntensity: 0.45, roughness: 0.35, metalness: 0.1 });
    const traceGeo = new THREE.BoxGeometry(1, 1, 1);
    traceGeo.translate(0, 0, 0.5);
    const traceMat = new THREE.MeshBasicMaterial({ color: PAL.trace, transparent: true, opacity: 0.8 });
    const hoverGeo = new THREE.PlaneGeometry(w * cell, h * cell);
    hoverGeo.rotateX(-Math.PI / 2);
    const hoverMat = new THREE.MeshBasicMaterial({ visible: false });
    const hiGeo = new THREE.PlaneGeometry(cell * 0.94, cell * 0.94);
    hiGeo.rotateX(-Math.PI / 2);
    const hiMat = new THREE.MeshBasicMaterial({ color: PAL.trace, transparent: true, opacity: 0.12, depthWrite: false });
    const all = [segGeo, segMat, linkGeo, headGeo, headMat, eyeGeo, eyeMat, foodGeo, foodMat, traceGeo, traceMat, hoverGeo, hoverMat, hiGeo, hiMat];
    return {
      segs, links, headGeo, headMat, eyeGeo, eyeMat, foodGeo, foodMat, traceGeo, traceMat, hoverGeo, hoverMat, hiGeo, hiMat,
      dispose() {
        all.forEach((x) => x.dispose());
        segs.dispose();
        links.dispose();
      },
    };
  }, [w, h, cell]);

  const headRef = useRef<THREE.Group>(null);
  const foodRef = useRef<THREE.Mesh>(null);
  const traceRef = useRef<THREE.Mesh>(null);
  const hiRef = useRef<THREE.Mesh>(null);
  const shown = useRef<unknown>(null);
  const anim = useRef<Anim | null>(null);
  const lastFood = useRef<string>("");

  // Decide once per new board whether it is exactly one recorded move away from what is on screen
  useEffect(() => {
    const now = performance.now();
    const body = snake?.body ?? [];
    const prev = readSnake(frame.from);
    const prevBody = prev?.body ?? [];
    const recordedMove = !!frame.action && singleMove(prevBody, body);
    const continuous = recordedMove && deepEqualState(shown.current, frame.from);
    const animate = continuous && !lowMotion;
    anim.current = {
      from: animate ? body.map((_, i) => prevBody[Math.min(i, prevBody.length - 1)]) : body,
      to: body,
      t0: now,
      dur: DUR.move * 1000,
      traceFrom: recordedMove ? prevBody[0] : null,
      traceTo: recordedMove ? body[0] : null,
      traceT0: continuous && !lowMotion ? now : now - 10000,
      foodT0: anim.current?.foodT0 ?? 0,
    };
    const fk = snake?.food ? `${snake.food.x},${snake.food.y}` : "";
    if (fk !== lastFood.current) {
      anim.current.foodT0 = lastFood.current && !lowMotion ? now + (animate ? DUR.move * 600 : 0) : now - 10000;
      lastFood.current = fk;
    }
    shown.current = frame.state;
    invalidate();
    // frame.state identity marks a new board
  }, [frame.state, frame.key]);

  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), o: new THREE.Object3D(), a: new THREE.Vector3(), b: new THREE.Vector3(), c: new THREE.Color(), c2: new THREE.Color(), pts: [] as THREE.Vector3[] }), []);

  useFrame(() => {
    const a = anim.current;
    if (!a) return;
    const now = performance.now();
    const t = clamp01((now - a.t0) / a.dur);
    const e = easeInOutCubic(t);
    const n = a.to.length;
    const segH = cell * 0.5;
    const { o } = tmp;
    while (tmp.pts.length < n) tmp.pts.push(new THREE.Vector3());
    for (let i = 0; i < n; i++) {
      toWorld(a.from[i], tmp.a);
      toWorld(a.to[i], tmp.b);
      tmp.pts[i].lerpVectors(tmp.a, tmp.b, e);
    }
    // Body segments, tapering toward the tail
    parts.segs.count = Math.max(0, n - 1);
    for (let i = 1; i < n; i++) {
      const f = n > 2 ? (i - 1) / (n - 2) : 0;
      const s = 1 - f * 0.28;
      o.position.set(tmp.pts[i].x, TOP + 0.05 + (segH * s) / 2, tmp.pts[i].z);
      o.rotation.set(0, 0, 0);
      o.scale.set(s, s, s);
      o.updateMatrix();
      parts.segs.setMatrixAt(i - 1, o.matrix);
      parts.segs.setColorAt(i - 1, tmp.c.set(PAL.body).lerp(tmp.c2.set(PAL.bodyTail), f));
    }
    parts.segs.instanceMatrix.needsUpdate = true;
    if (parts.segs.instanceColor) parts.segs.instanceColor.needsUpdate = true;
    // Links between neighbouring segments keep the body continuous while it moves
    parts.links.count = Math.max(0, n - 1);
    for (let i = 0; i < n - 1; i++) {
      const p = tmp.pts[i];
      const q = tmp.pts[i + 1];
      const len = p.distanceTo(q);
      const f = n > 2 ? i / (n - 2) : 0;
      const s = 1 - f * 0.28;
      o.position.set((p.x + q.x) / 2, TOP + 0.05 + (segH * s * 0.8) / 2, (p.z + q.z) / 2);
      o.rotation.set(0, Math.atan2(q.x - p.x, q.z - p.z), 0);
      o.scale.set(cell * 0.5 * s, segH * s * 0.8, Math.max(0.001, len));
      o.updateMatrix();
      parts.links.setMatrixAt(i, o.matrix);
      parts.links.setColorAt(i, tmp.c.set(PAL.body).lerp(tmp.c2.set(PAL.bodyTail), f));
    }
    parts.links.instanceMatrix.needsUpdate = true;
    if (parts.links.instanceColor) parts.links.instanceColor.needsUpdate = true;

    const head = headRef.current;
    if (head) {
      head.visible = n > 0;
      if (n > 0) {
        head.position.set(tmp.pts[0].x, TOP + 0.05 + (cell * 0.62) / 2, tmp.pts[0].z);
        const dir = snake?.direction ?? (frame.action as Dir | null) ?? "up";
        head.rotation.set(0, HEAD_ROT[dir], 0);
      }
    }
    const food = foodRef.current;
    if (food && snake?.food) {
      const ft = clamp01((now - a.foodT0) / (DUR.slow * 1000));
      const s = ft <= 0 ? 0.001 : easeOutBack(ft);
      toWorld(snake.food, tmp.a);
      food.position.set(tmp.a.x, TOP + 0.05 + cell * 0.36, tmp.a.z);
      food.scale.setScalar(Math.max(0.001, s));
      food.rotation.set(0, Math.PI / 4, 0);
    }
    const tr = traceRef.current;
    if (tr) {
      tr.visible = !!(a.traceFrom && a.traceTo);
      if (a.traceFrom && a.traceTo) {
        const tt = easeOutCubic(clamp01((now - a.traceT0) / (DUR.trace * 1000)));
        toWorld(a.traceFrom, tmp.a);
        toWorld(a.traceTo, tmp.b);
        const len = tmp.a.distanceTo(tmp.b);
        tr.position.set(tmp.a.x, TOP + 0.05 + cell * 0.72, tmp.a.z);
        tr.rotation.set(0, Math.atan2(tmp.b.x - tmp.a.x, tmp.b.z - tmp.a.z), 0);
        tr.scale.set(cell * 0.16, cell * 0.06, Math.max(0.001, len * tt));
      }
    }
    const busy = t < 1 || now - a.traceT0 < DUR.trace * 1000 || now - a.foodT0 < DUR.slow * 1000;
    if (busy) invalidate();
  });

  const anchors = useMemo(() => {
    const hd = snake?.body[0];
    if (!hd || !frame.probes) return null;
    const out = {} as Record<Dir, THREE.Vector3>;
    (Object.keys(DELTA) as Dir[]).forEach((d) => {
      out[d] = toWorld({ x: hd.x + DELTA[d].x, y: hd.y + DELTA[d].y });
    });
    return out;
  }, [snake?.body[0]?.x, snake?.body[0]?.y, frame.probes, w, h, cell]);

  const onMove = (e: ThreeEvent<PointerEvent>) => {
    const x = Math.floor(e.point.x / cell + w / 2);
    const y = Math.floor(e.point.z / cell + h / 2);
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const idx = snake?.body.findIndex((p) => p.x === x && p.y === y) ?? -1;
    const what = idx === 0 ? "snake head" : idx > 0 ? `snake body, segment ${idx}` : snake?.food && snake.food.x === x && snake.food.y === y ? "food" : "empty cell";
    onHover(`x ${x}, y ${y}: ${what}`);
    const hi = hiRef.current;
    if (hi) {
      hi.visible = true;
      hi.position.set((x + 0.5 - w / 2) * cell, TOP + 0.055, (y + 0.5 - h / 2) * cell);
    }
    invalidate();
  };
  const onOut = () => {
    onHover(null);
    if (hiRef.current) hiRef.current.visible = false;
    invalidate();
  };

  return (
    <group>
      <mesh geometry={board.slabGeo} material={board.slabMat} receiveShadow />
      <primitive object={board.cells} />
      <AxisLabels cols={w} rows={h} cell={cell} y={TOP + 0.005} rim={0.35} />
      <primitive object={parts.segs} />
      <primitive object={parts.links} />
      <group ref={headRef}>
        <mesh geometry={parts.headGeo} material={parts.headMat} castShadow />
        <mesh geometry={parts.eyeGeo} material={parts.eyeMat} position={[-cell * 0.17, cell * 0.2, -cell * 0.3]} />
        <mesh geometry={parts.eyeGeo} material={parts.eyeMat} position={[cell * 0.17, cell * 0.2, -cell * 0.3]} />
      </group>
      {snake?.food ? <mesh ref={foodRef} geometry={parts.foodGeo} material={parts.foodMat} castShadow /> : null}
      <mesh ref={traceRef} geometry={parts.traceGeo} material={parts.traceMat} visible={false} />
      <mesh ref={hiRef} geometry={parts.hiGeo} material={parts.hiMat} visible={false} />
      <mesh geometry={parts.hoverGeo} material={parts.hoverMat} position={[0, TOP + 0.06, 0]} onPointerMove={onMove} onPointerDown={onMove} onPointerOut={onOut} />
      <Probes decision={frame.probes} anchors={anchors} cell={cell} baseY={TOP + 0.05} lowMotion={lowMotion} />
      <CameraRig half={BOARD / 2 + 0.55} height={cell * 1.2} lowMotion={lowMotion} />
    </group>
  );
}

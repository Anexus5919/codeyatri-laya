import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { BoardFrame } from "../lib/derive";
import { deepEqualState, read2048 } from "../lib/derive";
import { planMove, tileHeight, type MovePlan } from "../lib/game2048";
import { DUR, clamp01, easeInOutCubic, easeOutBack } from "../lib/motion";
import { PAL, tileColors } from "../lib/palette";
import type { Dir } from "../lib/types";
import { AxisLabels, BOARD, CameraRig, LabelCache, Probes, roundedBox, std, useDisposable } from "./shared";

const SLAB_H = 0.5;
const TOP = SLAB_H / 2;
const POOL = 32;

interface Sprite {
  from: [number, number];
  to: [number, number];
  value: number;
  after: number; // value shown once the slide ends (doubled for merges)
  kind: "tile" | "merge" | "spawn";
  hideAfter: boolean; // second tile of a merge disappears into the first
}

interface Anim {
  sprites: Sprite[];
  t0: number;
  animate: boolean;
}

function staticSprites(grid: number[][]): Sprite[] {
  const out: Sprite[] = [];
  grid.forEach((row, r) => row.forEach((v, c) => v && out.push({ from: [r, c], to: [r, c], value: v, after: v, kind: "tile", hideAfter: false })));
  return out;
}

function planSprites(plan: MovePlan): Sprite[] {
  const out: Sprite[] = [];
  const seen = new Set<string>();
  for (const s of plan.sprites) {
    const key = `${s.to[0]},${s.to[1]}`;
    if (s.mergedValue) {
      const first = !seen.has(key);
      seen.add(key);
      out.push({ from: s.from, to: s.to, value: s.value, after: s.mergedValue, kind: "merge", hideAfter: !first });
    } else out.push({ from: s.from, to: s.to, value: s.value, after: s.value, kind: "tile", hideAfter: false });
  }
  if (plan.spawn) out.push({ from: plan.spawn.at, to: plan.spawn.at, value: plan.spawn.value, after: plan.spawn.value, kind: "spawn", hideAfter: false });
  return out;
}

export function Scene2048({ frame, lowMotion, onHover }: { frame: BoardFrame; lowMotion: boolean; onHover: (t: string | null) => void }) {
  const invalidate = useThree((s) => s.invalidate);
  const grid = read2048(frame.state);
  const n = grid?.length ?? 4;
  const cell = BOARD / n;
  const pos = (r: number, c: number) => [(c + 0.5 - n / 2) * cell, (r + 0.5 - n / 2) * cell] as const;

  const res = useDisposable(() => {
    const slabGeo = roundedBox(BOARD + 0.6, SLAB_H, BOARD + 0.6, 0.22);
    const slabMat = std(PAL.slab, { roughness: 0.85 });
    const wellGeo = roundedBox(cell * 0.9, 0.04, cell * 0.9, 0.08);
    const wellMat = std(PAL.cellA, { roughness: 0.95 });
    const tileGeo = roundedBox(cell * 0.86, 1, cell * 0.86, cell * 0.1);
    const labelGeo = new THREE.PlaneGeometry(cell * 0.8, cell * 0.8);
    labelGeo.rotateX(-Math.PI / 2);
    const hoverGeo = new THREE.PlaneGeometry(BOARD, BOARD);
    hoverGeo.rotateX(-Math.PI / 2);
    const hoverMat = new THREE.MeshBasicMaterial({ visible: false });
    const hiMat = new THREE.MeshBasicMaterial({ color: PAL.trace, transparent: true, opacity: 0.25, depthWrite: false });
    const hiGeo = new THREE.PlaneGeometry(cell * 0.94, cell * 0.94);
    hiGeo.rotateX(-Math.PI / 2);
    const mats = new Map<number, THREE.MeshStandardMaterial>();
    const labels = new LabelCache();
    const all = [slabGeo, slabMat, wellGeo, wellMat, tileGeo, labelGeo, hoverGeo, hoverMat, hiMat, hiGeo];
    return {
      slabGeo, slabMat, wellGeo, wellMat, tileGeo, labelGeo, hoverGeo, hoverMat, hiMat, hiGeo, labels,
      tileMat(v: number) {
        let m = mats.get(v);
        if (!m) {
          const c = tileColors(v);
          m = std(c.fill, { roughness: 0.38, metalness: 0.06, emissive: new THREE.Color(c.fill), emissiveIntensity: v >= 128 ? 0.28 : 0.1 });
          mats.set(v, m);
        }
        return m;
      },
      dispose() {
        all.forEach((x) => x.dispose());
        mats.forEach((m) => m.dispose());
        labels.dispose();
      },
    };
  }, [n, cell]);

  // A fixed pool of tile groups, updated in place every frame
  const pool = useMemo(
    () =>
      Array.from({ length: POOL }, () => {
        const g = new THREE.Group();
        const body = new THREE.Mesh(res.tileGeo);
        body.castShadow = true;
        const label = new THREE.Mesh(res.labelGeo);
        g.add(body, label);
        g.visible = false;
        return { g, body, label, value: -1 };
      }),
    [res],
  );

  const shown = useRef<unknown>(null);
  const anim = useRef<Anim | null>(null);
  const hiRef = useRef<THREE.Mesh>(null);

  useEffect(() => {
    if (!grid) return;
    const fromGrid = read2048(frame.from);
    const continuous = !!fromGrid && !!frame.action && deepEqualState(shown.current, frame.from);
    const plan = continuous && fromGrid && frame.action ? planMove(fromGrid, grid, frame.action as Dir) : null;
    anim.current = plan && !lowMotion ? { sprites: planSprites(plan), t0: performance.now(), animate: true } : { sprites: staticSprites(grid), t0: 0, animate: false };
    shown.current = frame.state;
    invalidate();
  }, [frame.state, frame.key]);

  useFrame(() => {
    const a = anim.current;
    if (!a) return;
    const now = performance.now();
    const t = a.animate ? clamp01((now - a.t0) / (DUR.move * 1000 * 1.5)) : 1;
    const slide = easeInOutCubic(clamp01(t / 0.62));
    const pop = clamp01((t - 0.62) / 0.38);
    pool.forEach((p, k) => {
      const s = a.sprites[k];
      if (!s) {
        p.g.visible = false;
        return;
      }
      const [fx, fz] = pos(s.from[0], s.from[1]);
      const [tx, tz] = pos(s.to[0], s.to[1]);
      const done = t >= 0.62;
      const value = done ? s.after : s.value;
      let scale = 1;
      let visible = true;
      if (s.kind === "spawn") {
        scale = t < 0.62 ? 0 : easeOutBack(pop);
        visible = scale > 0.001;
      } else if (s.kind === "merge") {
        if (done && s.hideAfter) visible = false;
        if (done && !s.hideAfter) scale = 1 + Math.sin(pop * Math.PI) * 0.14;
      }
      p.g.visible = visible;
      if (!visible) return;
      const hgt = tileHeight(value) * cell * 0.9;
      p.g.position.set(fx + (tx - fx) * slide, TOP + 0.04, fz + (tz - fz) * slide);
      p.g.scale.set(scale, scale, scale);
      p.body.scale.set(1, hgt, 1);
      p.body.position.y = hgt / 2;
      p.label.position.y = hgt + 0.012;
      if (p.value !== value) {
        p.value = value;
        p.body.material = res.tileMat(value);
        p.label.material = res.labels.get(String(value), tileColors(value).text);
      }
    });
    if (t < 1) invalidate();
  });

  const anchors = useMemo(() => {
    if (!frame.probes) return null;
    const off = BOARD / 2 + cell * 0.36;
    return {
      up: new THREE.Vector3(0, 0, -off),
      down: new THREE.Vector3(0, 0, off),
      left: new THREE.Vector3(-off, 0, 0),
      right: new THREE.Vector3(off, 0, 0),
    } as Record<Dir, THREE.Vector3>;
  }, [frame.probes, cell]);

  const onMove = (e: ThreeEvent<PointerEvent>) => {
    if (!grid) return;
    const c = Math.floor(e.point.x / cell + n / 2);
    const r = Math.floor(e.point.z / cell + n / 2);
    if (r < 0 || c < 0 || r >= n || c >= n) return;
    onHover(`grid[${r}][${c}] = ${grid[r][c]}`);
    if (hiRef.current) {
      const [x, z] = pos(r, c);
      hiRef.current.visible = true;
      hiRef.current.position.set(x, TOP + 0.05, z);
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
      <mesh geometry={res.slabGeo} material={res.slabMat} receiveShadow />
      <AxisLabels cols={n} rows={n} cell={cell} y={TOP + 0.005} rim={0.3} />
      {Array.from({ length: n * n }, (_, k) => {
        const [x, z] = pos(Math.floor(k / n), k % n);
        return <mesh key={k} geometry={res.wellGeo} material={res.wellMat} position={[x, TOP + 0.02, z]} receiveShadow />;
      })}
      {pool.map((p, k) => (
        <primitive key={k} object={p.g} />
      ))}
      <mesh ref={hiRef} geometry={res.hiGeo} material={res.hiMat} visible={false} />
      <mesh geometry={res.hoverGeo} material={res.hoverMat} position={[0, TOP + 0.9, 0]} onPointerMove={onMove} onPointerDown={onMove} onPointerOut={onOut} />
      <Probes decision={frame.probes} anchors={anchors} cell={cell * 0.55} baseY={TOP - 0.2} lowMotion={lowMotion} />
      <CameraRig half={BOARD / 2 + cell * 0.55} height={cell * 0.9} lowMotion={lowMotion} />
    </group>
  );
}

import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import type { DecisionView } from "../lib/derive";
import { PAL } from "../lib/palette";
import { DUR, clamp01, easeOutCubic } from "../lib/motion";
import type { Dir } from "../lib/types";
import { DIRS } from "../lib/types";

export const BOARD = 10;

// Creates three.js resources once per dependency change and frees GPU memory when they go away
export function useDisposable<T extends { dispose: () => void }>(factory: () => T, deps: unknown[]): T {
  const obj = useMemo(factory, deps);
  useEffect(() => () => obj.dispose(), [obj]);
  return obj;
}

export function roundedBox(w: number, h: number, d: number, r: number): THREE.BufferGeometry {
  return new RoundedBoxGeometry(w, h, d, 3, r);
}

export function std(color: string, opts: Partial<THREE.MeshStandardMaterialParameters> = {}): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.08, ...opts });
}

// ---------- number textures for 2048 tiles ----------

export class LabelCache {
  private map = new Map<string, THREE.MeshBasicMaterial>();

  get(text: string, color: string): THREE.MeshBasicMaterial {
    const key = `${text}|${color}`;
    let m = this.map.get(key);
    if (!m) {
      const c = document.createElement("canvas");
      c.width = 256;
      c.height = 256;
      const ctx = c.getContext("2d");
      if (ctx) {
        const size = text.length >= 4 ? 92 : text.length === 3 ? 112 : 138;
        ctx.font = `700 ${size}px "JetBrains Mono Variable", Consolas, monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = color;
        ctx.fillText(text, 128, 136);
      }
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      m = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false });
      this.map.set(key, m);
    }
    return m;
  }

  dispose(): void {
    for (const m of this.map.values()) {
      m.map?.dispose();
      m.dispose();
    }
    this.map.clear();
  }
}

// Column and row indices on the board rim, so hover coordinates can be read against the board
export function AxisLabels({ cols, rows, cell, y, rim }: { cols: number; rows: number; cell: number; y: number; rim: number }) {
  const res = useDisposable(() => {
    const labels = new LabelCache();
    const geo = new THREE.PlaneGeometry(Math.min(rim * 0.9, cell * 0.5), Math.min(rim * 0.9, cell * 0.5));
    geo.rotateX(-Math.PI / 2);
    return {
      labels, geo,
      dispose() {
        labels.dispose();
        geo.dispose();
      },
    };
  }, [cell, rim]);
  const color = "#ad9482";
  const top = -(rows / 2) * cell - rim / 2;
  const left = -(cols / 2) * cell - rim / 2;
  return (
    <group>
      {Array.from({ length: cols }, (_, c) => (
        <mesh key={`c${c}`} geometry={res.geo} material={res.labels.get(String(c), color)} position={[(c + 0.5 - cols / 2) * cell, y, top]} />
      ))}
      {Array.from({ length: rows }, (_, r) => (
        <mesh key={`r${r}`} geometry={res.geo} material={res.labels.get(String(r), color)} position={[left, y, (r + 0.5 - rows / 2) * cell]} />
      ))}
    </group>
  );
}

// ---------- camera: fits the board to any canvas size, with a restrained pointer offset ----------

const tmpV = new THREE.Vector3();

function fitDistance(corners: THREE.Vector3[], dir: THREE.Vector3, target: THREE.Vector3, vfov: number, aspect: number, margin: number): number {
  const tanV = Math.tan(vfov / 2);
  const tanH = tanV * aspect;
  const fwd = dir.clone().multiplyScalar(-1).normalize();
  const right = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0)).normalize();
  const up = new THREE.Vector3().crossVectors(right, fwd).normalize();
  const fits = (dist: number) => {
    const pos = target.clone().addScaledVector(dir, dist);
    for (const q of corners) {
      tmpV.subVectors(q, pos);
      const z = tmpV.dot(fwd);
      if (z <= 0.1) return false;
      if (Math.abs(tmpV.dot(right) / (z * tanH)) > margin || Math.abs(tmpV.dot(up) / (z * tanV)) > margin) return false;
    }
    return true;
  };
  let lo = 2;
  let hi = 200;
  for (let k = 0; k < 28; k++) {
    const mid = (lo + hi) / 2;
    if (fits(mid)) hi = mid;
    else lo = mid;
  }
  return hi;
}

export function CameraRig({ half, height, lowMotion }: { half: number; height: number; lowMotion: boolean }) {
  const { camera, size, gl, invalidate } = useThree();
  const target = useRef({ az: 0, el: 0 });
  const cur = useRef({ az: 0, el: 0 });
  const corners = useMemo(() => {
    const out: THREE.Vector3[] = [];
    for (const x of [-half, half]) for (const z of [-half, half]) for (const y of [-0.6, height]) out.push(new THREE.Vector3(x, y, z));
    return out;
  }, [half, height]);

  useEffect(() => {
    const el = gl.domElement;
    const onMove = (e: PointerEvent) => {
      if (lowMotion || e.pointerType === "touch") return;
      const r = el.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
      const ny = ((e.clientY - r.top) / r.height) * 2 - 1;
      target.current = { az: nx * 0.07, el: -ny * 0.045 };
      invalidate();
    };
    const onLeave = () => {
      target.current = { az: 0, el: 0 };
      invalidate();
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
    };
  }, [gl, invalidate, lowMotion]);

  useEffect(() => {
    if (lowMotion) {
      target.current = { az: 0, el: 0 };
      cur.current = { az: 0, el: 0 };
    }
    invalidate();
  }, [lowMotion, size.width, size.height, invalidate]);

  useFrame((_, dt) => {
    const cam = camera as THREE.PerspectiveCamera;
    const k = lowMotion ? 1 : 1 - Math.exp(-Math.min(dt, 0.1) * 7);
    cur.current.az += (target.current.az - cur.current.az) * k;
    cur.current.el += (target.current.el - cur.current.el) * k;
    // Wide, short stages get a steeper view so the board can use the height it has
    const aspectNow = size.width / Math.max(1, size.height);
    const el = 1.04 + THREE.MathUtils.clamp((aspectNow - 1.5) * 0.11, 0, 0.2) + cur.current.el;
    const az = cur.current.az;
    const dir = new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)).normalize();
    const look = new THREE.Vector3(0, 0, 0.15);
    const aspect = size.width / Math.max(1, size.height);
    const dist = fitDistance(corners, dir, look, THREE.MathUtils.degToRad(cam.fov), aspect, 0.97);
    cam.position.copy(look).addScaledVector(dir, dist);
    cam.lookAt(look);
    cam.updateProjectionMatrix();
    if (Math.abs(target.current.az - cur.current.az) > 1e-4 || Math.abs(target.current.el - cur.current.el) > 1e-4) invalidate();
  });
  return null;
}

// ---------- decision probes: one column per asked direction, height = Laya's yes-probability ----------

export function Probes({ decision, anchors, cell, baseY, lowMotion }: { decision: DecisionView | null; anchors: Record<Dir, THREE.Vector3> | null; cell: number; baseY: number; lowMotion: boolean }) {
  const invalidate = useThree((s) => s.invalidate);
  const res = useDisposable(() => {
    const column = new THREE.BoxGeometry(1, 1, 1);
    column.translate(0, 0.5, 0);
    const disc = new THREE.CylinderGeometry(0.5, 0.5, 1, 32);
    const bar = new THREE.BoxGeometry(1, 1, 1);
    const cone = new THREE.ConeGeometry(0.5, 1, 4);
    const chosen = std(PAL.ember, { emissive: new THREE.Color(PAL.ember), emissiveIntensity: 0.55, roughness: 0.4 });
    const other = std("#d9c6b2", { emissive: new THREE.Color("#6d4a3c"), emissiveIntensity: 0.35, roughness: 0.6, transparent: true, opacity: 0.92 });
    const ring = new THREE.MeshBasicMaterial({ color: "#5e2f29", transparent: true, opacity: 0.85 });
    const ringChosen = new THREE.MeshBasicMaterial({ color: PAL.ember, transparent: true, opacity: 0.5 });
    const cross = new THREE.MeshBasicMaterial({ color: "#7f685c", transparent: true, opacity: 0.75 });
    return {
      column, disc, bar, cone, chosen, other, ring, ringChosen, cross,
      dispose() {
        [column, disc, bar, cone, chosen, other, ring, ringChosen, cross].forEach((x) => x.dispose());
      },
    };
  }, []);
  const groupRef = useRef<THREE.Group>(null);
  const cols = useRef<Partial<Record<Dir, THREE.Mesh>>>({});
  const start = useRef(0);
  const key = decision ? `${decision.origin}-${decision.i}-${decision.step}-${decision.ts}` : "none";

  useEffect(() => {
    start.current = performance.now();
    invalidate();
  }, [key, invalidate]);

  useFrame(() => {
    if (!decision) return;
    const t = lowMotion ? 1 : clamp01((performance.now() - start.current) / (DUR.slow * 1000 * 1.4));
    const e = easeOutCubic(t);
    for (const d of DIRS) {
      const m = cols.current[d];
      const dv = decision.dirs.find((x) => x.dir === d);
      if (m && dv?.pYes != null) m.scale.set(cell * 0.4, Math.max(0.001, dv.pYes * cell * 2.2 * e), cell * 0.4);
    }
    if (t < 1) invalidate();
  });

  if (!decision || !anchors) return null;
  return (
    <group ref={groupRef}>
      {DIRS.map((d) => {
        const dv = decision.dirs.find((x) => x.dir === d);
        const p = anchors[d];
        if (!dv) return null;
        if (dv.asked === false || dv.pYes === null) {
          return (
            <group key={d} position={[p.x, baseY + 0.02, p.z]}>
              <mesh geometry={res.bar} material={res.cross} rotation={[0, Math.PI / 4, 0]} scale={[cell * 0.5, 0.02, cell * 0.08]} />
              <mesh geometry={res.bar} material={res.cross} rotation={[0, -Math.PI / 4, 0]} scale={[cell * 0.5, 0.02, cell * 0.08]} />
            </group>
          );
        }
        return (
          <group key={d} position={[p.x, baseY, p.z]}>
            <mesh geometry={res.disc} material={dv.chosen ? res.ringChosen : res.ring} scale={[cell * 0.62, 0.02, cell * 0.62]} />
            <mesh
              ref={(m) => {
                if (m) cols.current[d] = m;
                else delete cols.current[d];
              }}
              geometry={res.column}
              material={dv.chosen ? res.chosen : res.other}
              castShadow
            />
          </group>
        );
      })}
    </group>
  );
}

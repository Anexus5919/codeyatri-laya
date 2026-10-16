// The one WebGL canvas: a demand-driven scene that renders only when a board changes, an animation runs
// or the pointer moves. Loaded lazily so the rest of the page is usable before three.js arrives.

import { useEffect } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { BoardFrame } from "../lib/derive";
import { store } from "../lib/store";
import { Scene2048 } from "./Scene2048";
import { SnakeScene } from "./SnakeScene";

// @react-three/fiber 9.8 still creates a THREE.Clock internally, which three r183+ reports as deprecated.
// Drop exactly that notice; every other three.js message goes to the console unchanged.
THREE.setConsoleFunction((type: string, message: string, ...params: unknown[]) => {
  if (type === "warn" && message.startsWith("THREE.Clock: This module has been deprecated")) return;
  const out = type === "error" ? console.error : type === "warn" ? console.warn : console.log;
  out(message, ...params);
});

function Lights() {
  return (
    <>
      <hemisphereLight args={["#f3efe8", "#1a1a1d", 1.6]} />
      <directionalLight
        position={[-6, 14, 7]}
        intensity={3.4}
        color="#fbf6ee"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-9}
        shadow-camera-right={9}
        shadow-camera-top={9}
        shadow-camera-bottom={-9}
        shadow-camera-near={1}
        shadow-camera-far={40}
        shadow-bias={-0.0004}
      />
      <pointLight position={[0, 5, -10]} intensity={26} distance={30} color="#d8dde3" />
    </>
  );
}

// Re-render on visibility return and stop asking for frames while the tab is hidden
function Housekeeping() {
  const { gl, invalidate } = useThree();
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible") invalidate();
    };
    const onLost = (e: Event) => {
      e.preventDefault();
      store.set({ webgl: "lost" });
    };
    document.addEventListener("visibilitychange", onVis);
    gl.domElement.addEventListener("webglcontextlost", onLost);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      gl.domElement.removeEventListener("webglcontextlost", onLost);
    };
  }, [gl, invalidate]);
  return null;
}

export default function Arena3D({ game, frame, lowMotion, onHover }: { game: string; frame: BoardFrame; lowMotion: boolean; onHover: (t: string | null) => void }) {
  return (
    <Canvas
      className="arena-canvas"
      frameloop="demand"
      dpr={[1, 1.75]}
      shadows="percentage"
      flat
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ fov: 30, near: 0.5, far: 200, position: [0, 18, 14] }}
      onCreated={() => store.set({ webgl: "ok" })}
      aria-hidden="true"
    >
      <Housekeeping />
      <Lights />
      {game === "snake" ? <SnakeScene frame={frame} lowMotion={lowMotion} onHover={onHover} /> : <Scene2048 frame={frame} lowMotion={lowMotion} onHover={onHover} />}
    </Canvas>
  );
}

import { Component, lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from "react";
import type { BoardFrame } from "../lib/derive";
import { setRenderer, store, useStore } from "../lib/store";
import { BoardSvg } from "./BoardSvg";

const Arena3D = lazy(() => import("../arena3d/Arena3D"));

function detectWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2") || c.getContext("webgl")) as WebGLRenderingContext | null;
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}

class GlBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    store.set({ webgl: "unavailable" });
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function useWebglSupport(): boolean {
  return useMemo(detectWebGL, []);
}

export function use3D(game: string | null | undefined): { use3d: boolean; reason: string | null } {
  const renderer = useStore((s) => s.renderer);
  const webgl = useStore((s) => s.webgl);
  const supported = useWebglSupport();
  if (game !== "snake" && game !== "2048") return { use3d: false, reason: null };
  if (renderer === "2d") return { use3d: false, reason: null };
  if (!supported || webgl === "unavailable") return { use3d: false, reason: "WebGL is not available in this browser, showing the 2D board" };
  if (webgl === "lost") return { use3d: false, reason: "The WebGL context was lost, showing the 2D board" };
  return { use3d: true, reason: null };
}

export function ArenaStage({ game, frame }: { game: string | null | undefined; frame: BoardFrame }) {
  const lowMotion = useStore((s) => s.lowMotion);
  const { use3d, reason } = use3D(game);
  const [hover, setHover] = useState<string | null>(null);
  const onHover = useCallback((t: string | null) => setHover(t), []);
  const svg = <BoardSvg game={game} frame={frame} onHover={onHover} />;
  return (
    <div className={`stage-canvas${use3d ? " is-3d" : " is-2d"}`}>
      {use3d ? (
        <GlBoundary fallback={svg}>
          <Suspense
            fallback={
              <div className="stage-loading">
                {svg}
                <span className="stage-note">Loading the 3D board</span>
              </div>
            }
          >
            <Arena3D game={game as string} frame={frame} lowMotion={lowMotion} onHover={onHover} />
          </Suspense>
        </GlBoundary>
      ) : (
        svg
      )}
      {hover ? (
        <div className="stage-hover" aria-hidden="true">
          {hover}
        </div>
      ) : null}
      {reason ? <div className="stage-note">{reason}</div> : null}
    </div>
  );
}

export function RendererToggle({ game }: { game: string | null | undefined }) {
  const renderer = useStore((s) => s.renderer);
  const supported = useWebglSupport();
  const webgl = useStore((s) => s.webgl);
  if (game !== "snake" && game !== "2048") return null;
  const can3d = supported && webgl !== "unavailable";
  const is3d = renderer !== "2d" && can3d && webgl !== "lost";
  return (
    <div className="seg seg-small" role="group" aria-label="Board renderer">
      <button type="button" aria-pressed={is3d} disabled={!can3d} title={can3d ? "Three.js arena" : "WebGL unavailable"} onClick={() => setRenderer("3d")}>
        3D
      </button>
      <button type="button" aria-pressed={!is3d} onClick={() => setRenderer("2d")} title="Lightweight SVG board">
        2D
      </button>
    </div>
  );
}

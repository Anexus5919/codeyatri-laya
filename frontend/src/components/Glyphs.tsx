// Custom SVG glyphs. Every status glyph has a distinct shape so meaning never rests on colour alone.

import type { ReactNode } from "react";
import type { Act, Dir } from "../lib/types";

type P = { size?: number; className?: string; title?: string };

function Svg({ size = 20, className, title, children, viewBox = "0 0 24 24" }: P & { children: ReactNode; viewBox?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

// Brand: four arms, one lit, the shape of every decision on this page
export function BrandMark({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false" className="brand-mark">
      <rect x="1" y="1" width="38" height="38" rx="10" fill="var(--c-surface-2)" stroke="var(--c-line-strong)" />
      <path d="M20 6 L25 15 H15 Z" fill="var(--c-red)" />
      <path d="M20 34 L15 25 H25 Z" fill="var(--c-text-4)" />
      <path d="M6 20 L15 15 V25 Z" fill="var(--c-text-4)" />
      <path d="M34 20 L25 25 V15 Z" fill="var(--c-text-4)" />
      <circle cx="20" cy="20" r="3.2" fill="var(--c-text)" />
    </svg>
  );
}

const ROT: Record<Dir, number> = { up: 0, right: 90, down: 180, left: 270 };
// Doom moves reuse the arrow; a strafe is a sideways arrow, back is a downward one
const MOVE_ROT: Partial<Record<Act, number>> = { forward: 0, backward: 180, strafe_left: 270, strafe_right: 90 };
const ARROW = "M12 3.5 L19 11 H14.6 V20.5 H9.4 V11 H5 Z";

function TurnGlyph({ left, big, size, className, title }: P & { left: boolean; big: boolean }) {
  // An arc with an arrowhead; the big turn sweeps further
  const arc = big ? "M17.5 17 A7 7 0 1 0 6.6 9.4" : "M15.5 16.5 A6 6 0 0 0 8 7.6";
  const head = big ? "M3.6 7.9 L7.4 6.9 L7.7 11 Z" : "M5.2 6.6 L9.1 5.9 L8.9 10 Z";
  return (
    <Svg size={size} className={className} title={title}>
      <g transform={left ? undefined : "translate(24 0) scale(-1 1)"}>
        <path d={arc} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        <path d={head} fill="currentColor" />
      </g>
    </Svg>
  );
}

export function DirGlyph({ dir, size = 22, className, title }: P & { dir: Act }) {
  if (dir in ROT || dir in MOVE_ROT) {
    const rot = dir in ROT ? ROT[dir as Dir] : MOVE_ROT[dir] ?? 0;
    return (
      <Svg size={size} className={className} title={title}>
        <g transform={`rotate(${rot} 12 12)`}>
          <path d={ARROW} fill="currentColor" />
        </g>
      </Svg>
    );
  }
  if (dir === "shoot")
    return (
      <Svg size={size} className={className} title={title}>
        <circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" strokeWidth="2.2" />
        <path d="M12 2.5 V7 M12 17 V21.5 M2.5 12 H7 M17 12 H21.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="12" cy="12" r="1.8" fill="currentColor" />
      </Svg>
    );
  if (dir === "use")
    return (
      <Svg size={size} className={className} title={title}>
        <path d="M6 21 V4.5 a1.5 1.5 0 0 1 1.5 -1.5 H16.5 a1.5 1.5 0 0 1 1.5 1.5 V21" fill="none" stroke="currentColor" strokeWidth="2.2" />
        <path d="M3.5 21 H20.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="14.6" cy="12.5" r="1.4" fill="currentColor" />
      </Svg>
    );
  if (dir === "turn_around")
    return (
      <Svg size={size} className={className} title={title}>
        <path d="M8 20 V10 a4.5 4.5 0 0 1 9 0 V14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M13.2 13.2 L17 18.5 L20.8 13.2 Z" fill="currentColor" />
      </Svg>
    );
  const left = dir === "turn_left" || dir === "turn_left_big";
  return <TurnGlyph left={left} big={dir === "turn_left_big" || dir === "turn_right_big"} size={size} className={className} title={title} />;
}

export function AppliedGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <path d="M7.5 12.3 L10.6 15.3 L16.6 8.8" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function RejectedGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <path d="M8.5 8.5 L15.5 15.5 M15.5 8.5 L8.5 15.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
    </Svg>
  );
}

export function FallbackGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <path d="M12 3 L21.5 20 H2.5 Z" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinejoin="round" />
      <path d="M12 9.5 V14" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="12" cy="17.2" r="1.4" fill="currentColor" />
    </Svg>
  );
}

export function PendingGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.2" strokeDasharray="3.2 3" />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" />
    </Svg>
  );
}

export function NotAskedGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M5.8 18.2 L18.2 5.8" stroke="currentColor" strokeWidth="2" />
    </Svg>
  );
}

export function ShieldGlyph({ size = 16, className, title, state }: P & { state: "ok" | "bad" | "wait" }) {
  return (
    <Svg size={size} className={className} title={title}>
      <path d="M12 2.8 L19.5 5.6 V11.6 C19.5 16.2 16.4 19.6 12 21.2 C7.6 19.6 4.5 16.2 4.5 11.6 V5.6 Z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      {state === "ok" ? <path d="M8.6 12 L11 14.4 L15.6 9.6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /> : null}
      {state === "bad" ? <path d="M9.3 9.3 L14.7 14.7 M14.7 9.3 L9.3 14.7" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" /> : null}
      {state === "wait" ? <circle cx="12" cy="12" r="1.8" fill="currentColor" /> : null}
    </Svg>
  );
}

export function SimGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <rect x="3" y="5" width="18" height="12" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M8 21 H16 M12 17 V21" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M7 9 L10 11 L7 13 M12 13 H16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function GlobeGlyph({ size = 14, className, title }: P) {
  return (
    <Svg size={size} className={className} title={title}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M3 12 H21 M12 3 C15 6 15 18 12 21 C9 18 9 6 12 3" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </Svg>
  );
}

// Navigation icons
export function IconArena({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <path d="M12 3 L21 8 V16 L12 21 L3 16 V8 Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M3 8 L12 13 L21 8 M12 13 V21" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="12" cy="8" r="1.6" fill="currentColor" />
    </Svg>
  );
}

export function IconSessions({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <rect x="3.5" y="4" width="17" height="4.5" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <rect x="3.5" y="10" width="17" height="4.5" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <rect x="3.5" y="16" width="17" height="4.5" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="6.6" cy="6.25" r="1.1" fill="currentColor" />
    </Svg>
  );
}

export function IconHistory({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <path d="M4 18 V6 M4 12 H8 M10 18 V9 M10 13 H14 M16 18 V4 M16 11 H20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M2.5 20.5 H21.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </Svg>
  );
}

export function IconTiming({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <path d="M3 15 L7 11 L10 14 L14 7 L17 12 L21 9" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M3 20 H21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </Svg>
  );
}

export function IconAudit({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <rect x="2.5" y="9" width="6" height="6" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <rect x="9" y="9" width="6" height="6" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <rect x="15.5" y="9" width="6" height="6" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 3 V7 M12 17 V21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </Svg>
  );
}

export function IconBoard({ size = 22 }: P) {
  return (
    <Svg size={size}>
      <path d="M9 20 V8 H15 V20 M3 20 V12 H9 M15 20 V14 H21 V20 M2 20 H22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}

export function IconMotion({ size = 20, low }: P & { low: boolean }) {
  return (
    <Svg size={size}>
      <path d="M3 12 C6 6 9 18 12 12 C15 6 18 18 21 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" opacity={low ? 0.35 : 1} />
      {low ? <path d="M3 12 H21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /> : null}
    </Svg>
  );
}

export function IconBack({ size = 16 }: P) {
  return (
    <Svg size={size}>
      <path d="M20 12 H5 M11 6 L5 12 L11 18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconChevron({ size = 16, dir = "right" }: P & { dir?: "left" | "right" }) {
  return (
    <Svg size={size}>
      <path d={dir === "right" ? "M9 5 L16 12 L9 19" : "M15 5 L8 12 L15 19"} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function IconLive({ size = 16 }: P) {
  return (
    <Svg size={size}>
      <circle cx="12" cy="12" r="3" fill="currentColor" />
      <path d="M7.5 7.5 a6.4 6.4 0 0 0 0 9 M16.5 7.5 a6.4 6.4 0 0 1 0 9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </Svg>
  );
}

export function GameGlyph({ game, size = 18 }: { game: string | null | undefined; size?: number }) {
  if (game === "snake")
    return (
      <Svg size={size}>
        <path d="M4 18 H13 a3 3 0 0 0 0 -6 H10 a3 3 0 0 1 0 -6 H18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="19.5" cy="6" r="1.7" fill="currentColor" />
      </Svg>
    );
  if (game === "doom")
    return (
      <Svg size={size}>
        <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M12 2.5 V7.5 M12 16.5 V21.5 M2.5 12 H7.5 M16.5 12 H21.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </Svg>
    );
  if (game === "2048")
    return (
      <Svg size={size}>
        <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.6" fill="currentColor" opacity="0.9" />
        <rect x="13" y="3.5" width="7.5" height="7.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <rect x="13" y="13" width="7.5" height="7.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.8" />
      </Svg>
    );
  return (
    <Svg size={size}>
      <path d="M4 4 H20 V20 H4 Z M4 10 H20 M4 15 H20 M10 4 V20 M15 4 V20" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </Svg>
  );
}

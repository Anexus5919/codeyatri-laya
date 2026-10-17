import { useEffect, useState } from "react";
import { fmtInt, isNum, type BoardFrame } from "../lib/derive";
import { useStore } from "../lib/store";

const WEAPON: Record<number, string> = { 1: "fist", 2: "pistol", 3: "shotgun", 4: "chaingun", 5: "rocket launcher", 6: "plasma rifle", 7: "BFG" };

// Doom's stage: the screen Laya's decision was made on, saved by the runner (--frames), with the engine's numbers.
// The next image loads off screen and replaces the shown one only once it has arrived, so a capture that is being
// written at that moment never blanks the stage; it is simply tried again on the next decision.
export function DoomScreen({ frame }: { frame: BoardFrame }) {
  const sessionId = useStore((s) => s.sessionId);
  const following = useStore((s) => s.selection.mode === "live" && s.feed?.meta?.status === "live");
  const [missing, setMissing] = useState<Record<string, true>>({});
  const [shown, setShown] = useState<{ sid: string | null; src: string } | null>(null);
  const step = frame.imageStep;
  // History: the step's own screen, then the one before it (after the final action there is no newer one)
  const candidates = step === null ? [] : following ? ["latest"] : [String(step), ...(step > 1 ? [String(step - 1)] : [])];
  const pick = candidates.find((c) => following || !missing[`${sessionId}#${c}`]) ?? null;
  const want = sessionId && pick ? `api/frame?id=${encodeURIComponent(sessionId)}&step=${pick}${pick === "latest" ? `&k=${encodeURIComponent(frame.key)}` : ""}` : null;

  useEffect(() => {
    if (!want) return;
    let alive = true;
    const img = new Image();
    img.onload = () => alive && setShown({ sid: sessionId, src: want });
    img.onerror = () => {
      // Live: keep the last good frame and try again with the next decision. History: try the step before.
      if (alive && !following && pick) setMissing((m) => ({ ...m, [`${sessionId}#${pick}`]: true }));
    };
    img.src = want;
    return () => {
      alive = false;
    };
  }, [want, sessionId, following, pick]);

  const src = shown && shown.sid === sessionId ? shown.src : null;
  const nothing = !following && candidates.length > 0 && candidates.every((c) => missing[`${sessionId}#${c}`]);
  const st = { ...((frame.from ?? {}) as Record<string, unknown>), ...((frame.state ?? {}) as Record<string, unknown>) };
  const weapon = isNum(st.weapon) ? (st.weapon < 0 ? "no weapon" : WEAPON[st.weapon] ?? "weapon") : null;
  const hud: [string, string][] = [
    ["Health", isNum(st.health) ? fmtInt(st.health) : "n/a"],
    ["Armor", isNum(st.armor) ? fmtInt(st.armor) : "n/a"],
    [weapon ? weapon.charAt(0).toUpperCase() + weapon.slice(1) : "Weapon", isNum(st.ammo) && isNum(st.weapon) && st.weapon > 1 ? `${fmtInt(st.ammo)} rounds` : weapon ? "" : "n/a"],
    ["Kills", isNum(st.kills) ? fmtInt(st.kills) : "n/a"],
    ["Game time", isNum(st.tic) ? `${(st.tic / 35).toFixed(1)} s` : "n/a"],
  ];
  return (
    <div className="doom-screen">
      <div className="doom-frame">
        {src && !nothing ? (
          <img src={src} alt={`Game screen at step ${step ?? ""}`} />
        ) : nothing || !want ? (
          <p className="doom-noframe">
            No screen capture for this step. Runs started with <code>--frames</code> save the screen at every decision; the game window shows the game live while it plays.
          </p>
        ) : null}
      </div>
      <dl className="doom-hud num">
        {hud.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v || " "}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

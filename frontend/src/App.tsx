import { useEffect } from "react";
import { MotionConfig } from "motion/react";
import { Backdrop, EnvBand, Rail, TopBar } from "./components/Chrome";
import { useStore } from "./lib/store";
import { ArenaView } from "./views/ArenaView";
import { AuditView } from "./views/AuditView";
import { HistoryView } from "./views/HistoryView";
import { SessionsView } from "./views/SessionsView";
import { TimingView } from "./views/TimingView";

const TITLES = { arena: "Live arena", sessions: "Sessions", history: "Decision history", timing: "Timing", audit: "Audit" } as const;

export function App() {
  const view = useStore((s) => s.view);
  const low = useStore((s) => s.lowMotion);
  const envKind = useStore((s) => s.feed?.meta?.summary?.env_kind);

  useEffect(() => {
    document.documentElement.dataset.motion = low ? "low" : "full";
  }, [low]);
  useEffect(() => {
    document.title = `CodeYatri | Laya Decision Viewer | ${TITLES[view]}`;
  }, [view]);

  return (
    <MotionConfig reducedMotion={low ? "always" : "user"}>
      <Backdrop />
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="shell" data-env={envKind ?? "unknown"}>
        <Rail />
        <div className="main-col">
          <TopBar />
          <EnvBand />
          <main id="main" className="main" tabIndex={-1}>
            {view === "arena" ? <ArenaView /> : null}
            {view === "sessions" ? <SessionsView /> : null}
            {view === "history" ? <HistoryView /> : null}
            {view === "timing" ? <TimingView /> : null}
            {view === "audit" ? <AuditView /> : null}
          </main>
        </div>
      </div>
    </MotionConfig>
  );
}

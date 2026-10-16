"use strict";

// Every value on this page comes from the run logs served by arena_web.py

const DIRS = ["up", "down", "left", "right"];
const POLL_MS = 400;
const SESSIONS_MS = 2000;
const VERIFY_MS = 3000;
const LIVE_AGE_S = 15;
const KEEP_ITEMS = 400;
const FEED_ROWS = 150;
const FALLBACK_WARN = 0.08;
const FALLBACK_BAD = 0.10;
const SNAKE_WIN_FOODS = 15;

const ARROW = {
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5.5 12.5L12 19l6.5-6.5"/></svg>',
  left: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5M11.5 5.5L5 12l6.5 6.5"/></svg>',
  right: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12.5 5.5L19 12l-6.5 6.5"/></svg>',
};
const GAME_ICON = {
  snake: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 17h9a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h8"/><circle cx="19" cy="5" r="1.6"/></svg>',
  "2048": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>',
};

const $ = (id) => document.getElementById(id);

const app = { follow: true, sessions: [], newest: null, root: "", s: null, error: null, pickerSig: "", gridSig: "" };
const busy = { session: false, sessions: false, verify: false };

function emptySession(sid) {
  return {
    sid, game: null, folder: "", after: 0, eafter: 0, lines: [], decisions: [], start: null, end: null,
    final: null, summary: null, ageS: null, verify: null, loaded: false, version: 0, rendered: -1,
  };
}

/* ---------- helpers ---------- */

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function isNum(v) { return typeof v === "number" && Number.isFinite(v); }
function pct(p, digits = 1) { return isNum(p) ? `${(p * 100).toFixed(digits)}%` : "-"; }
function num(v) { return isNum(v) ? Math.round(v).toLocaleString("en-US") : "-"; }
function shortId(sid) { return String(sid || "").slice(0, 8); }
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }
function gameLabel(g) { return g === "snake" ? "Snake" : g === "2048" ? "2048" : (g || "Unknown game"); }

function fmtAge(sec) {
  if (!isNum(sec)) return "-";
  if (sec < 1) return "just now";
  if (sec < 60) return `${Math.floor(sec)} s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
  return `${Math.floor(sec / 86400)} d ago`;
}
function fmtTime(value) {
  const d = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  if (d.toDateString() === new Date().toDateString()) return t;
  return `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${t}`;
}

async function getJSON(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).error || msg; } catch (_) { /* not json */ }
    throw new Error(msg);
  }
  return r.json();
}

function loop(fn, ms) {
  const tick = async () => {
    try { await fn(); } catch (e) { console.warn(e); }
    setTimeout(tick, ms);
  };
  tick();
}

/* ---------- polling ---------- */

async function pollSessions() {
  if (busy.sessions) return;
  busy.sessions = true;
  try {
    const r = await getJSON("/api/sessions");
    app.sessions = r.sessions || [];
    app.newest = r.newest;
    app.root = r.root || "";
    app.error = null;
    if (r.newest && (app.follow || !app.s) && (!app.s || app.s.sid !== r.newest)) switchTo(r.newest);
  } catch (e) {
    app.error = "Viewer server unreachable";
  } finally {
    busy.sessions = false;
  }
  renderPicker();
  renderChrome();
}

async function pollSession() {
  const s = app.s;
  if (!s || busy.session) return;
  busy.session = true;
  try {
    const r = await getJSON(`/api/session?id=${encodeURIComponent(s.sid)}&after=${s.after}&eafter=${s.eafter}`);
    if (app.s === s) absorb(s, r);
    app.error = null;
  } catch (e) {
    if (app.s === s) app.error = e.message === "Failed to fetch" ? "Viewer server unreachable" : `Session: ${e.message}`;
  } finally {
    busy.session = false;
  }
  render();
}

async function pollVerify() {
  const s = app.s;
  if (!s || busy.verify) return;
  busy.verify = true;
  try {
    const r = await getJSON(`/api/verify?id=${encodeURIComponent(s.sid)}`);
    if (app.s === s) s.verify = r;
  } catch (e) {
    if (app.s === s) s.verify = { error: e.message };
  } finally {
    busy.verify = false;
  }
  renderChrome();
}

function absorb(s, r) {
  if (r.reset) { s.lines = []; s.decisions = []; s.version++; }
  if (r.lines && r.lines.length) {
    s.lines.push(...r.lines);
    if (s.lines.length > KEEP_ITEMS) s.lines.splice(0, s.lines.length - KEEP_ITEMS);
    s.version++;
  }
  let newDecisions = 0;
  for (const e of r.events || []) {
    if (e.type === "decision") { s.decisions.push(e); newDecisions++; }
  }
  if (newDecisions) {
    if (s.decisions.length > KEEP_ITEMS) s.decisions.splice(0, s.decisions.length - KEEP_ITEMS);
    s.version++;
  }
  if (!!r.session_end !== !!s.end || !!r.final !== !!s.final || !!r.session_start !== !!s.start || !s.loaded) s.version++;
  s.after = r.next_after;
  s.eafter = r.next_events_after;
  s.game = r.game;
  s.folder = r.folder;
  s.start = r.session_start;
  s.end = r.session_end;
  s.final = r.final;
  s.summary = r.summary;
  s.ageS = r.age_s;
  s.loaded = true;
}

function switchTo(sid) {
  if (!sid || (app.s && app.s.sid === sid)) return;
  app.s = emptySession(sid);
  app.gridSig = "";
  render();
  pollSession();
  pollVerify();
}

/* ---------- derived data ---------- */

function lastLine(s) { return s.lines.length ? s.lines[s.lines.length - 1] : null; }

function latestState(s) {
  const l = lastLine(s);
  if (l && l.state_after && typeof l.state_after === "object") return l.state_after;
  if (s.final && s.final.state && typeof s.final.state === "object") return s.final.state;
  return null;
}

function hasFacts(f) { return f && typeof f === "object" && DIRS.some((d) => typeof f[d] === "string" && f[d].trim()); }

function commonPrefix(texts) {
  let p = texts[0];
  for (const t of texts) { let i = 0; while (i < p.length && i < t.length && p[i] === t[i]) i++; p = p.slice(0, i); }
  return p;
}
function commonSuffix(texts) {
  const rev = texts.map((t) => [...t].reverse().join(""));
  return [...commonPrefix(rev)].reverse().join("");
}

// The questions carry the same stem plus one fact per direction; strip the shared parts and map by direction
function factsFromQuestions(qs) {
  if (!Array.isArray(qs) || !qs.length) return null;
  const texts = qs.map((q) => String(q));
  let stem = "";
  let parts = texts;
  if (texts.length > 1) {
    let pre = commonPrefix(texts);
    if (pre.length < Math.min(...texts.map((t) => t.length))) {
      // Cut back to the end of a sentence so the fact keeps its own opening words
      const ends = [". ", "? ", "! ", ": ", "\n"].map((m) => { const i = pre.lastIndexOf(m); return i < 0 ? 0 : i + m.length; });
      const best = Math.max(...ends);
      pre = best ? pre.slice(0, best) : pre.slice(0, pre.lastIndexOf(" ") + 1);
    }
    let suf = commonSuffix(texts.map((t) => t.slice(pre.length)));
    const k = suf.indexOf(" ");
    suf = k >= 0 ? suf.slice(k) : "";
    const cut = texts.map((t) => t.slice(pre.length, t.length - suf.length).trim());
    if (pre.trim().length >= 12 && cut.every(Boolean)) { parts = cut; stem = pre.trim(); }
  }
  const first = parts.map((t) => { const m = t.toLowerCase().match(/\b(up|down|left|right)\b/); return m ? m[1] : null; });
  const facts = {};
  if (parts.length === 4 && first.every(Boolean) && new Set(first).size === 4) parts.forEach((t, i) => { facts[first[i]] = t; });
  else if (parts.length === 4) DIRS.forEach((d, i) => { facts[d] = parts[i]; });
  else parts.forEach((t, i) => { if (first[i] && !facts[first[i]]) facts[first[i]] = t; });
  return { facts, stem };
}

function findLast(arr, pred) {
  for (let i = arr.length - 1; i >= 0; i--) if (pred(arr[i])) return arr[i];
  return null;
}

// The decision event is written before the move is sent, so it can be one step ahead of the submission log
function currentDecision(s) {
  const line = lastLine(s);
  const ev = s.decisions.length ? s.decisions[s.decisions.length - 1] : null;
  const done = !!(s.summary && s.summary.done);
  if (ev && (!line || ev.step >= line.step)) {
    const match = findLast(s.lines, (l) => l.step === ev.step && l.action === ev.chosen);
    const parsed = match ? factsFromQuestions((match.decision || {}).questions) : null;
    const evFacts = hasFacts(ev.facts);
    return {
      step: ev.step,
      probs: ev.probabilities || (match && match.decision && match.decision.probabilities) || {},
      ptrue: ev.p_true || null,
      chosen: ev.chosen,
      source: ev.source,
      layaChoice: ev.laya_choice,
      facts: evFacts ? ev.facts : parsed && parsed.facts,
      factsFrom: evFacts ? "events" : parsed ? "questions" : null,
      stem: parsed && parsed.stem,
      decideMs: isNum(ev.decide_ms) ? ev.decide_ms : match && match.timing && match.timing.decide_ms,
      status: match ? match.result : done ? "not sent" : "pending",
    };
  }
  if (line) {
    const d = line.decision || {};
    const e = findLast(s.decisions, (x) => x.step === line.step && x.chosen === line.action);
    const parsed = factsFromQuestions(d.questions);
    const evFacts = e && hasFacts(e.facts);
    return {
      step: line.step,
      probs: d.probabilities || {},
      ptrue: e ? e.p_true : null,
      chosen: d.chosen || line.action,
      source: d.source,
      layaChoice: e ? e.laya_choice : null,
      facts: evFacts ? e.facts : parsed && parsed.facts,
      factsFrom: evFacts ? "events" : parsed ? "questions" : null,
      stem: parsed && parsed.stem,
      decideMs: line.timing && line.timing.decide_ms,
      status: line.result,
    };
  }
  return null;
}

/* ---------- rendering ---------- */

function render() {
  renderChrome();
  const s = app.s;
  if (!s) return;
  if (s.version === s.rendered) return;
  s.rendered = s.version;
  renderBoard(s);
  renderDecision(s);
  renderTiming(s);
  renderFeed(s);
}

function pill(cls, html, title) {
  return `<span class="pill ${cls}"${title ? ` title="${esc(title)}"` : ""}>${html}</span>`;
}

function renderChrome() {
  renderPills();
  renderStrip();
  renderRail();
}

function renderPills() {
  const s = app.s;
  const out = [];
  if (app.error) out.push(pill("bad", `<span class="dot"></span>${esc(app.error)}`));
  if (!s) {
    out.push(pill("muted", `<span class="dot"></span>No session in the runs folder yet`));
    $("pills").innerHTML = out.join("");
    return;
  }
  const sum = s.summary || {};
  if (s.game) out.push(pill("game", `${GAME_ICON[s.game] || ""}${esc(gameLabel(s.game))}`));
  out.push(pill("", `<span class="k">Session</span>${esc(shortId(s.sid))}`, s.sid));

  if (!s.loaded) out.push(pill("muted", `<span class="dot"></span>Loading`));
  else if (sum.done) {
    const finalDone = s.final && typeof s.final.done === "boolean" ? s.final.done : true;
    const label = sum.won ? "Finished · Won" : finalDone ? "Finished" : "Ended";
    out.push(pill(sum.won ? "ok" : "", `<span class="dot"></span>${label.toUpperCase()}`));
  } else if (isNum(s.ageS) && s.ageS <= LIVE_AGE_S) out.push(pill("live", `<span class="dot"></span>LIVE`));
  else out.push(pill("warn", `<span class="dot"></span>IDLE · ${esc(fmtAge(s.ageS))}`, "No session_end and no new writes"));

  if (s.start && (s.start.model || s.start.device)) {
    out.push(pill("", `<span class="k">Model</span>${esc(s.start.model || "?")} · ${esc(s.start.device || "?")}`));
  } else {
    out.push(pill("muted", `<span class="k">Model</span>not logged`, "No session_start event for this session"));
  }

  const v = s.verify;
  if (!v) out.push(pill("muted", `<span class="dot"></span>Chain: checking`));
  else if (v.error) out.push(pill("bad", `<span class="dot"></span>Verify failed`, v.error));
  else if (v.pending) out.push(pill("muted", `<span class="dot"></span>Chain: no lines yet`));
  else {
    const problems = v.problems || [];
    const tip = problems.length ? problems.slice(0, 8).join("\n") : `verify_log: ${v.lines} lines, prev_hash and hash checked`;
    if (v.ok) out.push(pill("ok", `<span class="dot"></span>Chain verified · ${num(v.lines)}`, tip));
    else if (v.chain_ok === false) out.push(pill("bad", `<span class="dot"></span>Hash chain BROKEN`, tip));
    else out.push(pill("warn", `<span class="dot"></span>Chain OK · ${problems.length} issue${problems.length === 1 ? "" : "s"}`, tip));
  }

  if (sum.steps) {
    const share = sum.fallback_share || 0;
    const cls = share > FALLBACK_BAD ? "bad" : share > FALLBACK_WARN ? "warn" : "ok";
    out.push(pill(cls, `<span class="dot"></span><span class="k">Fallback</span>${pct(share)}`,
      `${sum.fallbacks} of ${sum.steps} applied moves used the fallback (limit 10%)`));
  } else {
    out.push(pill("muted", `<span class="k">Fallback</span>-`));
  }
  $("pills").innerHTML = out.join("");
}

function renderStrip() {
  const s = app.s;
  const sum = (s && s.summary) || {};
  $("st-steps").textContent = s && s.loaded ? num(sum.steps) : "-";
  $("st-rej").textContent = s && s.loaded ? num(sum.rejected) : "-";
  $("st-dec").textContent = s && s.loaded ? (s.start || sum.decisions ? num(sum.decisions) : "no events") : "-";
  $("st-age").textContent = s && s.loaded ? fmtAge(s.ageS) : "-";
  const segs = app.root.split(/[\\/]/).filter(Boolean);
  $("st-root").textContent = segs.length > 2 ? `...\\${segs.slice(-2).join("\\")}` : app.root || "-";
  $("st-root").title = app.root || "";
  const fb = $("follow-btn");
  fb.setAttribute("aria-pressed", app.follow ? "true" : "false");
  fb.title = app.follow ? "Following the newest session; switches automatically" : "Pinned to the chosen session";

  const sub = $("subtitle");
  if (!s) { sub.textContent = "Looking for sessions in the runs folder"; return; }
  const st = s.start;
  if (st) {
    const bits = [];
    if (st.agent_name) bits.push(`Agent <strong>${esc(st.agent_name)}</strong>`);
    if (st.design) bits.push(`design <strong>${esc(st.design)}</strong>`);
    if (st.ts) bits.push(`started ${esc(fmtTime(st.ts))}`);
    sub.innerHTML = bits.join(" · ");
  } else {
    sub.innerHTML = `No session_start event logged for this session`;
  }
}

function renderRail() {
  const g = app.s && app.s.game;
  $("rail-follow").classList.toggle("active", app.follow);
  for (const game of ["snake", "2048"]) {
    const el = $(`rail-${game}`);
    const any = app.sessions.some((x) => x.game === game);
    el.classList.toggle("active", g === game);
    el.style.opacity = any ? "" : "0.45";
    el.title = any ? `Newest ${gameLabel(game)} session` : `No ${gameLabel(game)} session yet`;
  }
}

function sessionStatus(x) {
  if (x.done) return x.won ? "won" : "finished";
  return isNum(x.age_s) && x.age_s <= LIVE_AGE_S ? "live" : "idle";
}

function renderPicker() {
  const sel = $("picker");
  const items = app.sessions.slice();
  const cur = app.s && app.s.sid;
  if (cur && !items.some((x) => x.session_id === cur)) items.unshift({ session_id: cur, game: app.s.game });
  const sig = JSON.stringify([cur, items.map((x) => [x.session_id, x.steps, x.points, sessionStatus(x)])]);
  if (sig === app.pickerSig || document.activeElement === sel) return;
  app.pickerSig = sig;
  if (!items.length) { sel.innerHTML = `<option value="">No sessions yet</option>`; return; }
  sel.innerHTML = items.map((x) => {
    const parts = [gameLabel(x.game), shortId(x.session_id)];
    if (isNum(x.steps)) parts.push(`${x.steps} moves`);
    if (isNum(x.points)) parts.push(`${x.points} pts`);
    if (x.mtime) parts.push(sessionStatus(x));
    if (x.mtime) parts.push(fmtTime(x.mtime));
    return `<option value="${esc(x.session_id)}"${x.session_id === cur ? " selected" : ""}>${esc(parts.join("  ·  "))}</option>`;
  }).join("");
}

/* board */

function renderBoard(s) {
  const state = latestState(s);
  const sum = s.summary || {};
  const line = lastLine(s);
  const game = s.game;
  let title = "Board";
  if (game === "snake") title = `Snake · ${state && state.width ? state.width : 12} x ${state && state.height ? state.height : 12}`;
  else if (game === "2048") title = "2048 · 4 x 4";
  $("board-title").textContent = title;
  $("board-sub").textContent = line ? `State after step ${line.step}${line.ts ? ` · ${fmtTime(line.ts)}` : ""}` : "No moves logged yet";

  const tag = $("board-tag");
  if (line) {
    tag.hidden = false;
    tag.className = `tag ${line.result === "rejected" ? "bad" : ""}`;
    tag.innerHTML = `Last ${esc(line.action)} · ${esc(line.result)}`;
  } else tag.hidden = true;

  $("board-empty").hidden = !!state;
  $("snake-canvas").hidden = !(state && game === "snake");
  $("board-2048").hidden = !(state && game === "2048");

  const banner = $("board-banner");
  if (sum.done) {
    const finalDone = s.final && typeof s.final.done === "boolean" ? s.final.done : true;
    const head = sum.won ? "Won" : finalDone ? "Game over" : "Session ended";
    const bits = [];
    if (isNum(sum.final_score)) bits.push(`final score ${num(sum.final_score)}`);
    if (game === "snake") bits.push(`${sum.foods} foods`);
    if (game === "2048") bits.push(`best tile ${num(sum.best_tile)}`);
    if (isNum(sum.points)) bits.push(`${num(sum.points)} pts`);
    banner.textContent = [head, ...bits].join(" · ");
    banner.className = `board-banner ${sum.won ? "ok" : ""}`;
    banner.hidden = false;
  } else banner.hidden = true;

  drawBoard();
  renderKpis(s);
  renderProgress(s);
}

function drawBoard() {
  const s = app.s;
  if (!s) return;
  const state = latestState(s);
  if (!state) return;
  const wrap = $("board-wrap");
  const banner = $("board-banner");
  const room = wrap.clientHeight - (banner.hidden ? 0 : banner.offsetHeight + 10);
  const size = Math.max(140, Math.floor(Math.min(wrap.clientWidth, room)) - 2);
  if (s.game === "snake") {
    const dec = currentDecision(s);
    drawSnake(state, size, dec && dec.status === "pending" ? dec.chosen : null);
  } else if (s.game === "2048") draw2048(state, size);
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function mix(a, b, t) {
  const pa = a.match(/\w\w/g).map((h) => parseInt(h, 16));
  const pb = b.match(/\w\w/g).map((h) => parseInt(h, 16));
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(",")})`;
}

const STEP = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

function drawSnake(state, size, nextDir) {
  const cv = $("snake-canvas");
  const dpr = window.devicePixelRatio || 1;
  cv.style.width = `${size}px`;
  cv.style.height = `${size}px`;
  cv.width = Math.round(size * dpr);
  cv.height = Math.round(size * dpr);
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const grid = Array.isArray(state.grid) ? state.grid : [];
  const H = state.height || grid.length || 12;
  const W = state.width || (grid[0] || []).length || 12;
  const pad = Math.max(10, size * 0.03);
  const cell = (size - 2 * pad) / Math.max(W, H);
  const ox = (size - cell * W) / 2;
  const oy = (size - cell * H) / 2;
  const inside = (p) => p && isNum(p.x) && isNum(p.y) && p.x >= 0 && p.y >= 0 && p.x < W && p.y < H;
  const cx = (p) => ox + (p.x + 0.5) * cell;
  const cy = (p) => oy + (p.y + 0.5) * cell;

  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = "#240a08";
  roundRect(ctx, 0, 0, size, size, 16);
  ctx.fill();
  ctx.strokeStyle = "#98635D";
  ctx.lineWidth = 2;
  roundRect(ctx, 1, 1, size - 2, size - 2, 15);
  ctx.stroke();

  const g = Math.max(1, cell * 0.06);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      ctx.fillStyle = (x + y) % 2 ? "#461a17" : "#3d1613";
      roundRect(ctx, ox + x * cell + g, oy + y * cell + g, cell - 2 * g, cell - 2 * g, cell * 0.16);
      ctx.fill();
    }
  }

  // Snake cells: the ordered list when present, otherwise the grid codes (1 body, 2 food, 3 head)
  let body = Array.isArray(state.snake) ? state.snake.filter(inside) : [];
  let food = inside(state.food) ? state.food : null;
  if (!body.length || !food) {
    const heads = [], rest = [];
    grid.forEach((row, y) => (row || []).forEach((v, x) => {
      if (v === 3) heads.push({ x, y });
      else if (v === 1) rest.push({ x, y });
      else if (v === 2 && !food) food = { x, y };
    }));
    if (!body.length) body = heads.concat(rest);
  }

  if (food) {
    const r = cell * 0.3;
    ctx.save();
    ctx.shadowColor = "rgba(95, 191, 127, 0.85)";
    ctx.shadowBlur = cell * 0.45;
    ctx.fillStyle = "#5FBF7F";
    ctx.beginPath();
    ctx.arc(cx(food), cy(food), r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    ctx.fillStyle = "rgba(255, 255, 255, 0.55)";
    ctx.beginPath();
    ctx.arc(cx(food) - r * 0.35, cy(food) - r * 0.35, r * 0.28, 0, Math.PI * 2);
    ctx.fill();
  }

  const ordered = Array.isArray(state.snake) && body.length === state.snake.length;
  const n = body.length;
  const colorAt = (i) => mix("F07C70", "8E302A", n > 1 ? i / (n - 1) : 0);
  if (ordered) {
    ctx.lineCap = "round";
    for (let i = n - 1; i > 0; i--) {
      const a = body[i], b = body[i - 1];
      if (Math.abs(a.x - b.x) + Math.abs(a.y - b.y) !== 1) continue;
      ctx.strokeStyle = colorAt(i);
      ctx.lineWidth = cell * 0.62;
      ctx.beginPath();
      ctx.moveTo(cx(a), cy(a));
      ctx.lineTo(cx(b), cy(b));
      ctx.stroke();
    }
  }
  for (let i = n - 1; i >= 1; i--) {
    const p = body[i];
    const sz = cell * 0.74;
    ctx.fillStyle = colorAt(i);
    roundRect(ctx, cx(p) - sz / 2, cy(p) - sz / 2, sz, sz, sz * 0.3);
    ctx.fill();
  }

  if (n) {
    const h = body[0];
    const sz = cell * 0.86;
    ctx.save();
    ctx.shadowColor = "rgba(213, 43, 39, 0.8)";
    ctx.shadowBlur = cell * 0.4;
    ctx.fillStyle = "#F8F0ED";
    roundRect(ctx, cx(h) - sz / 2, cy(h) - sz / 2, sz, sz, sz * 0.32);
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "#D52B27";
    ctx.lineWidth = Math.max(2, cell * 0.08);
    roundRect(ctx, cx(h) - sz / 2, cy(h) - sz / 2, sz, sz, sz * 0.32);
    ctx.stroke();
    let dir = STEP[state.direction] ? state.direction : null;
    if (!dir && ordered && n > 1) {
      const dx = h.x - body[1].x, dy = h.y - body[1].y;
      dir = dx > 0 ? "right" : dx < 0 ? "left" : dy > 0 ? "down" : "up";
    }
    const [fx, fy] = STEP[dir || "right"];
    const px = -fy, py = fx;
    ctx.fillStyle = "#35110F";
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(cx(h) + fx * cell * 0.17 + px * side * cell * 0.17, cy(h) + fy * cell * 0.17 + py * side * cell * 0.17, cell * 0.075, 0, Math.PI * 2);
      ctx.fill();
    }

    // The move Laya just chose and the game has not answered yet
    if (nextDir && STEP[nextDir]) {
      const [dx, dy] = STEP[nextDir];
      const t = { x: h.x + dx, y: h.y + dy };
      ctx.save();
      ctx.strokeStyle = "rgba(255, 90, 82, 0.95)";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 4]);
      if (inside(t)) {
        roundRect(ctx, ox + t.x * cell + g * 2, oy + t.y * cell + g * 2, cell - 4 * g, cell - 4 * g, cell * 0.2);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(255, 90, 82, 0.95)";
      const ax = cx(h) + dx * cell, ay = cy(h) + dy * cell, k = cell * 0.2;
      ctx.beginPath();
      ctx.moveTo(ax + dx * k, ay + dy * k);
      ctx.lineTo(ax - dx * k - dy * k, ay - dy * k + dx * k);
      ctx.lineTo(ax - dx * k + dy * k, ay - dy * k - dx * k);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
  }
}

function draw2048(state, size) {
  const el = $("board-2048");
  const gap = Math.max(6, Math.round(size * 0.025));
  el.style.width = `${size}px`;
  el.style.height = `${size}px`;
  el.style.setProperty("--gap", `${gap}px`);
  const tileSize = (size - 5 * gap - 4) / 4;
  el.style.setProperty("--tile-font", `${Math.round(tileSize * 0.4)}px`);
  const grid = Array.isArray(state.grid) ? state.grid : [];
  const sig = JSON.stringify(grid);
  if (sig === app.gridSig) return;
  app.gridSig = sig;
  const cells = [];
  for (let r = 0; r < 4; r++) {
    for (let c = 0; c < 4; c++) {
      const v = (grid[r] || [])[c];
      if (!isNum(v) || v <= 0) { cells.push('<div class="tile"></div>'); continue; }
      const digits = String(v).length;
      const cls = [v <= 2048 ? `v${v}` : "vbig", digits >= 3 ? `d${Math.min(5, digits)}` : ""].join(" ");
      cells.push(`<div class="tile ${cls}">${v}</div>`);
    }
  }
  el.innerHTML = cells.join("");
}

function kpi(label, value, note) {
  return `<div class="kpi"><div class="kpi-label">${esc(label)}</div><div class="kpi-value">${value}</div><div class="kpi-note">${esc(note || "")}</div></div>`;
}

function renderKpis(s) {
  const sum = s.summary || {};
  const pointsNote = sum.points_source === "session_end" ? "from session_end" : "computed from log";
  let html = "";
  if (s.game === "snake") {
    html = kpi("Foods eaten", num(sum.foods), `win at ${SNAKE_WIN_FOODS}`)
      + kpi("Snake length", num(sum.length), "cells")
      + kpi("Points", num(sum.points), pointsNote);
  } else if (s.game === "2048") {
    html = kpi("Score", num(sum.score), isNum(sum.final_score) ? `final ${num(sum.final_score)}` : "game score")
      + kpi("Best tile", num(sum.best_tile), "target 512")
      + kpi("Points", num(sum.points), pointsNote);
  }
  $("kpis").innerHTML = html;
}

function renderProgress(s) {
  const sum = s.summary || {};
  const box = $("progress");
  if (!isNum(sum.progress)) { box.hidden = true; return; }
  box.hidden = false;
  const fill = $("progress-fill");
  const value = $("progress-value");
  fill.style.width = `${Math.round(sum.progress * 1000) / 10}%`;
  fill.className = `progress-fill ${sum.unlocked ? "ok" : ""}`;
  value.className = sum.unlocked ? "ok" : "";
  let ticks = [];
  if (s.game === "snake") {
    $("progress-label").textContent = `Unlock target ${num(sum.target_points)} pts (${sum.target_foods} foods)`;
    value.textContent = sum.unlocked ? `Unlocked · ${num(sum.points)} pts` : `${sum.foods} / ${sum.target_foods} foods · ${num(sum.points)} / ${num(sum.target_points)} pts`;
    for (let i = 1; i < sum.target_foods; i++) ticks.push(i / sum.target_foods);
  } else {
    $("progress-label").textContent = `Unlock target: a ${num(sum.target_tile)} tile`;
    value.textContent = sum.unlocked ? `Unlocked · best tile ${num(sum.best_tile)}` : `best tile ${num(sum.best_tile)} of ${num(sum.target_tile)}`;
    ticks = [1 / 3, 2 / 3];
  }
  $("progress-ticks").innerHTML = ticks.map((t) => `<span style="left:calc(${(t * 100).toFixed(2)}% - 1px)"></span>`).join("");
  const scale = $("progress-scale");
  scale.hidden = s.game !== "2048";
  if (s.game === "2048") {
    const best = sum.best_tile || 0;
    scale.innerHTML = [[0, "64"], [1 / 3, "128"], [2 / 3, "256"], [1, "512"]]
      .map(([t, label]) => `<span class="${best >= Number(label) ? "hit" : ""}" style="left:${(t * 100).toFixed(2)}%">${label}</span>`).join("");
  }
}

/* decision */

function renderDecision(s) {
  const d = currentDecision(s);
  const rows = $("dir-rows");
  const badge = $("dec-source");
  if (!d) {
    $("dec-step").textContent = "";
    badge.hidden = true;
    $("dec-meta").innerHTML = "";
    rows.innerHTML = `<div class="empty">No decision logged yet</div>`;
    $("dec-foot").innerHTML = "";
    return;
  }
  $("dec-step").textContent = `step ${d.step}`;
  badge.hidden = false;
  const src = d.source === "fallback" ? "fallback" : "laya";
  badge.className = `source-badge ${src}`;
  badge.innerHTML = `<span class="dot"></span>${d.source ? esc(d.source) : "unknown"}`;
  badge.title = src === "fallback" ? "The move came from the fallback, not from Laya" : "The move is Laya's highest P(true)";

  const conf = d.probs ? d.probs[d.chosen] : null;
  const meta = [`<span class="chip">Confidence <strong>${pct(conf)}</strong></span>`];
  if (d.layaChoice && d.layaChoice !== d.chosen) meta.push(`<span class="chip pending">Laya picked <strong>${esc(d.layaChoice.toUpperCase())}</strong></span>`);
  if (isNum(d.decideMs)) meta.push(`<span class="chip">Decide <strong>${num(d.decideMs)}</strong> ms</span>`);
  if (d.status === "pending") meta.push(`<span class="chip pending">Sent · <strong>awaiting</strong></span>`);
  else if (d.status === "rejected") meta.push(`<span class="chip bad">Result <strong>rejected</strong></span>`);
  else if (d.status === "applied") meta.push(`<span class="chip">Result <strong>applied</strong></span>`);
  else meta.push(`<span class="chip">Result <strong>${esc(d.status)}</strong></span>`);
  $("dec-meta").innerHTML = meta.join("");

  rows.innerHTML = DIRS.map((dir) => {
    const p = d.probs ? d.probs[dir] : null;
    const chosen = dir === d.chosen;
    const layaAlt = d.layaChoice && d.layaChoice !== d.chosen && dir === d.layaChoice;
    const pt = d.ptrue && isNum(d.ptrue[dir]) ? `<span class="dir-ptrue">P(true) <strong>${d.ptrue[dir].toFixed(3)}</strong></span>` : "";
    const fact = d.facts && typeof d.facts[dir] === "string" && d.facts[dir].trim()
      ? `<div class="dir-fact" title="${esc(d.facts[dir])}">${esc(d.facts[dir])}</div>`
      : `<div class="dir-fact none">No fact text logged for this direction</div>`;
    const width = isNum(p) ? Math.max(0, Math.min(100, p * 100)) : 0;
    return `<div class="dir${chosen ? " chosen" : ""}">
      <div class="dir-main">
        <span class="dir-arrow">${ARROW[dir]}</span>
        <span class="dir-label"><span class="dir-name">${cap(dir)}</span>${chosen ? '<span class="dir-flag">Chosen</span>' : ""}${layaAlt ? '<span class="dir-flag alt">Laya pick</span>' : ""}</span>
        <span class="dir-nums">${pt}<span class="dir-prob">${pct(p)}</span></span>
      </div>
      <div class="dir-track"><div class="dir-fill" style="width:${width.toFixed(1)}%"></div></div>
      ${fact}
    </div>`;
  }).join("");

  const foot = [];
  if (d.stem) {
    foot.push(`<div class="dec-q"><div class="dec-q-label">Question asked once per direction</div>`
      + `<div class="dec-q-text">${esc(d.stem)} <em>+ that direction's fact</em></div></div>`);
  }
  const notes = [];
  if (d.factsFrom === "events") notes.push("Facts and raw P(true): events log");
  else if (d.factsFrom === "questions") notes.push("Facts: parsed from the logged questions");
  if (!d.ptrue || !Object.keys(d.ptrue).length) notes.push(d.source === "fallback" ? "no Laya P(true) on a fallback move" : "raw P(true) needs the events file");
  notes.push("bars: normalised probabilities");
  foot.push(`<div class="dec-src">${notes.join(" · ")}</div>`);
  $("dec-foot").innerHTML = foot.join("");
}

/* timing */

function renderTiming(s) {
  const t = (s.summary && s.summary.timing) || {};
  const rows = [
    ["decide_ms", "Decide", "Laya call"],
    ["api_ms", "Game API", "move round trip"],
    ["turn_ms", "Turn", "whole turn"],
  ];
  const ms = (v) => (isNum(v) ? `${num(v)}<span class="unit">ms</span>` : "-");
  let html = '<div class="th">Phase</div><div class="th">Last</div><div class="th">Mean</div><div class="th">p95</div>';
  for (const [key, name, note] of rows) {
    const x = t[key] || {};
    html += `<div class="lbl">${name}<small>${note}</small></div><div class="val last">${ms(x.last)}</div><div class="val">${ms(x.mean)}</div><div class="val">${ms(x.p95)}</div>`;
  }
  $("timing").innerHTML = html;
  const n = t.decide_ms && t.decide_ms.n;
  $("timing-sub").textContent = n ? `From ${num(n)} submission log lines` : "No timing logged yet";
}

/* feed */

function renderFeed(s) {
  const out = [];
  for (let i = s.lines.length - 1; i >= 0 && out.length < FEED_ROWS; i--) {
    const l = s.lines[i];
    const d = l.decision || {};
    const src = d.source === "fallback" ? "fallback" : "laya";
    const conf = isNum(d.confidence) ? d.confidence : d.probabilities ? d.probabilities[l.action] : null;
    const rejected = l.result === "rejected";
    out.push(`<div class="feed-row${rejected ? " rejected" : ""}">
      <span class="feed-step">${esc(l.step)}</span>
      <span class="feed-move">${ARROW[l.action] || ""}${esc(l.action)}</span>
      <span><span class="feed-src ${src}">${esc(d.source || "?")}</span></span>
      <span class="feed-conf">${pct(conf, 0)}</span>
      <span class="feed-res">${esc(l.result)}</span>
    </div>`);
  }
  $("feed").innerHTML = out.length ? out.join("") : `<div class="empty">No moves logged yet</div>`;
  const cnt = $("feed-count");
  const total = s.summary ? s.summary.lines : 0;
  cnt.hidden = !total;
  cnt.textContent = `${num(total)} lines`;
}

/* ---------- wiring ---------- */

function newestOf(game) {
  const x = app.sessions.find((y) => y.game === game);
  return x ? x.session_id : null;
}

function init() {
  const params = new URLSearchParams(location.search);
  const pinned = params.get("session");
  if (pinned) { app.follow = false; switchTo(pinned); }

  $("follow-btn").addEventListener("click", () => {
    app.follow = !app.follow;
    if (app.follow && app.newest) switchTo(app.newest);
    renderChrome();
  });
  $("rail-follow").addEventListener("click", () => {
    app.follow = true;
    if (app.newest) switchTo(app.newest);
    renderChrome();
  });
  for (const game of ["snake", "2048"]) {
    $(`rail-${game}`).addEventListener("click", () => {
      const sid = newestOf(game);
      if (!sid) return;
      app.follow = false;
      switchTo(sid);
      renderChrome();
    });
  }
  $("rail-sessions").addEventListener("click", () => {
    const sel = $("picker");
    sel.focus();
    try { if (sel.showPicker) sel.showPicker(); } catch (_) { /* needs a user gesture in some browsers */ }
  });
  $("rail-verify").addEventListener("click", () => pollVerify());
  $("picker").addEventListener("change", (e) => {
    const sid = e.target.value;
    if (!sid) return;
    app.follow = false;
    switchTo(sid);
    renderChrome();
  });
  $("picker").addEventListener("blur", () => { app.pickerSig = ""; renderPicker(); });

  if (window.ResizeObserver) new ResizeObserver(() => drawBoard()).observe($("board-wrap"));
  else window.addEventListener("resize", drawBoard);

  renderChrome();
  loop(pollSessions, SESSIONS_MS);
  loop(pollSession, POLL_MS);
  loop(pollVerify, VERIFY_MS);
}

document.addEventListener("DOMContentLoaded", init);

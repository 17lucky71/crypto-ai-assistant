// 바닐라 JS 프론트엔드. API 주소는 config.js 의 window.API_BASE_URL 에서 읽는다.
const API = (window.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const PAGE = 30;

const $ = (id) => document.getElementById(id);
const won = new Intl.NumberFormat("ko-KR");
const state = { conversationId: null, data: [], shown: PAGE, sending: false, series: [], range: 90 };

// ---------- 공통 요청 ----------
async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).join(", ") // Pydantic 검증 오류
      : body.detail || `요청 실패 (${res.status})`;
    throw new Error(detail);
  }
  return body;
}

function fmtPct(v) {
  if (v === null || v === undefined) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

// ---------- 서버 깨우기 (Render 무료 티어 콜드스타트 대응) ----------
async function waitForServer() {
  const status = $("serverStatus");
  const started = Date.now();
  const slowTimer = setTimeout(() => ($("wakeBanner").hidden = false), 3000);
  for (let i = 0; i < 20; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 15000);
      const res = await fetch(API + "/", { signal: ctrl.signal });
      clearTimeout(t);
      if (res.ok) {
        const info = await res.json();
        clearTimeout(slowTimer);
        $("wakeBanner").hidden = true;
        status.className = "pill pill-ok";
        status.textContent = info.storage === "firestore" ? "서버 연결됨" : "서버 연결됨 (임시 저장소)";
        return true;
      }
    } catch (_) { /* 아직 깨는 중 */ }
    status.textContent = `서버 깨우는 중… ${Math.round((Date.now() - started) / 1000)}초`;
    await new Promise((r) => setTimeout(r, 4000));
  }
  clearTimeout(slowTimer);
  status.className = "pill pill-bad";
  status.textContent = "서버 연결 실패";
  $("wakeBanner").hidden = false;
  $("wakeBanner").textContent = "서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.";
  return false;
}

// ---------- 요약 ----------
async function loadSummary() {
  try {
    const s = await api("/api/data/summary");
    $("sPeriod").textContent = s.period;
    $("sCount").textContent = `${won.format(s.count)}개`;
    const m = s.metrics || {};
    $("sLatest").textContent = m.latest ? `${won.format(m.latest.value)}원` : "-";
    const ch = m.change_30d_pct;
    $("sChange").textContent = fmtPct(ch);
    $("sChange").className = "value " + (ch > 0 ? "up" : ch < 0 ? "down" : "");
    $("sTrend").textContent = s.trend;
  } catch (e) {
    $("sTrend").textContent = `요약을 불러오지 못했어요: ${e.message}`;
  }
}

// ---------- 경보판 · 성적표 · 뉴스 · 알림 기록 (보너스) ----------
function fillList(ul, items, empty) {
  ul.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = empty;
    ul.appendChild(li);
    return;
  }
  items.forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    ul.appendChild(li);
  });
}

function setBar(el, valEl, pct, max) {
  // 0 을 가운데로 두고 왼쪽(하락)·오른쪽(상승)으로 막대를 그린다
  const w = Math.min(Math.abs(pct) / max, 1) * 50;
  el.style.width = `${w}%`;
  el.style.left = pct < 0 ? `${50 - w}%` : "50%";
  el.className = pct < 0 ? "neg" : "pos";
  valEl.textContent = fmtPct(pct);
  valEl.className = pct < 0 ? "down" : pct > 0 ? "up" : "";
}

async function loadSignal() {
  const board = $("risk");
  try {
    const g = await api("/api/signals");
    if (!g.available) {
      board.dataset.level = "none";
      $("lvName").textContent = "데이터 부족";
      $("lvDesc").textContent = g.message || "";
      return;
    }
    const lv = g.level;
    board.dataset.level = lv.key;
    $("lvName").textContent = lv.name;
    $("lvDesc").textContent = lv.desc;
    $("lvMeta").textContent = `${g.date} 종가 ${won.format(g.price)}원 · ${g.label} · 점수 ${g.score > 0 ? "+" : ""}${g.score}`;
    document.querySelectorAll("#lvScale li").forEach((li) => {
      const on = Number(li.dataset.step) === lv.step;
      li.classList.toggle("on", on);
      if (on) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });

    fillList($("sellReasons"), g.reasons.filter((r) => r.score < 0).map((r) => r.text), "지금은 뚜렷한 하락 근거가 없어요.");
    fillList($("holdReasons"), g.reasons.filter((r) => r.score > 0).map((r) => r.text), "버틸 근거가 보이지 않아요.");
    const neutral = g.reasons.filter((r) => r.score === 0).map((r) => r.text);
    $("neutralReasons").textContent = neutral.length ? `중립: ${neutral.join(" / ")}` : "";

    const bt = g.backtest;
    $("scHit").textContent = bt.sell.hit_rate_pct == null ? "-" : `${bt.sell.hit_rate_pct}%`;
    $("scHitSub").textContent = bt.sell.count ? `지난 ${bt.sell.count}번의 매도 신호 중 7일 뒤 실제로 내린 비율` : "아직 매도 신호가 나온 적이 없어요.";
    if (bt.after_sell_avg_pct != null) {
      const max = Math.max(Math.abs(bt.after_sell_avg_pct), Math.abs(bt.all_days_avg_pct), 1);
      setBar($("barSell"), $("valSell"), bt.after_sell_avg_pct, max);
      setBar($("barAll"), $("valAll"), bt.all_days_avg_pct, max);
      $("scBarsNote").textContent = bt.after_sell_avg_pct < bt.all_days_avg_pct
        ? "매도 신호 뒤가 평소보다 낮았어요. 신호에 팔았다면 손실을 줄였을 거예요."
        : "매도 신호 뒤가 평소보다 낮지 않았어요. 이 신호는 참고만 하세요.";
    }
    $("sigRange").textContent = `${eok(g.forecast.low)} ~ ${eok(g.forecast.high)}`;
  } catch (e) {
    board.dataset.level = "none";
    $("lvName").textContent = "불러오기 실패";
    $("lvDesc").textContent = e.message;
  }
}

async function loadNews() {
  const ul = $("newsList");
  try {
    const n = await api("/api/news?limit=5");
    ul.innerHTML = "";
    if (!n.items.length) {
      fillList(ul, [], n.error ? "뉴스를 가져오지 못했어요. 잠시 후 새로고침해 주세요." : "최근 7일 뉴스가 없어요.");
      return;
    }
    n.items.forEach((it) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = it.link; a.target = "_blank"; a.rel = "noopener";
      a.textContent = it.title;
      const sm = document.createElement("small");
      sm.textContent = `${it.source} ${it.published}`;
      li.append(a, sm);
      ul.appendChild(li);
    });
  } catch (e) {
    fillList(ul, [], "뉴스를 가져오지 못했어요. 잠시 후 새로고침해 주세요.");
  }
}

async function loadAlerts() {
  const ul = $("alertList");
  try {
    const rows = await api("/api/alerts/history?limit=5");
    ul.innerHTML = "";
    if (!rows.length) {
      fillList(ul, [], "아직 보낸 알림이 없어요. 위험 단계가 '주의' 이상이 되면 디스코드로 보내요.");
      return;
    }
    rows.forEach((r) => {
      const li = document.createElement("li");
      const tag = document.createElement("span");
      tag.className = `lv-tag step-${r.step}`;
      tag.textContent = r.kind === "release" ? "해제" : r.level;
      const t = document.createElement("span");
      t.textContent = `${r.date} 기준 · ${eok(r.price)}원`;
      const sm = document.createElement("small");
      sm.textContent = fmtDateTime(r.sent_at);
      li.append(tag, t, sm);
      ul.appendChild(li);
    });
  } catch (e) {
    fillList(ul, [], "알림 기록을 불러오지 못했어요.");
  }
}

// ---------- 채팅 ----------
function addMessage(role, text, toolsUsed) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text; // textContent 로 넣어 HTML 주입을 막는다
  if (toolsUsed && toolsUsed.length) {
    // (보너스) AI 가 답변을 위해 호출한 도구 표시
    const box = document.createElement("div");
    box.className = "tools-used";
    [...new Set(toolsUsed)].forEach((label) => {
      const tag = document.createElement("span");
      tag.textContent = `🔧 ${label}`;
      box.appendChild(tag);
    });
    el.appendChild(box);
  }
  $("messages").appendChild(el);
  $("messages").scrollTop = $("messages").scrollHeight;
  return el;
}

function showTyping() {
  const el = document.createElement("div");
  el.className = "msg assistant";
  el.innerHTML = '<span class="typing" aria-label="답변 작성 중"><span></span><span></span><span></span></span>';
  $("messages").appendChild(el);
  $("messages").scrollTop = $("messages").scrollHeight;
  return el;
}

function resetChat() {
  state.conversationId = null;
  $("chatTitle").textContent = "새 대화";
  $("messages").querySelectorAll(".msg:not(.intro)").forEach((n) => n.remove());
  $("suggestions").hidden = false;
  highlightConversation();
  $("chatInput").focus();
}

async function sendMessage(text) {
  if (state.sending || !text.trim()) return;
  state.sending = true;
  $("sendBtn").disabled = true;
  $("chatInput").value = "";
  $("suggestions").hidden = true;
  addMessage("user", text);
  const typing = showTyping();
  try {
    const res = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, conversation_id: state.conversationId }),
    });
    typing.remove();
    addMessage("assistant", res.reply, (res.tool_calls || []).map((t) => t.label));
    const isNew = !state.conversationId;
    state.conversationId = res.conversation_id;
    if (isNew) $("chatTitle").textContent = text.length > 30 ? text.slice(0, 30) + "…" : text;
    await loadConversations();
  } catch (e) {
    typing.remove();
    addMessage("error", `답변을 받지 못했어요: ${e.message}`);
  } finally {
    state.sending = false;
    $("sendBtn").disabled = false;
    $("chatInput").focus();
  }
}

// ---------- 대화 기록 ----------
function highlightConversation() {
  document.querySelectorAll(".conv-item").forEach((li) => {
    li.classList.toggle("active", li.dataset.id === state.conversationId);
  });
}

async function loadConversations() {
  try {
    const list = await api("/api/conversations");
    const ul = $("convList");
    ul.innerHTML = "";
    $("convEmpty").hidden = list.length > 0;
    list.forEach((c) => {
      const li = document.createElement("li");
      li.className = "conv-item";
      li.dataset.id = c.id;
      const t = document.createElement("div");
      t.className = "t";
      const strong = document.createElement("strong");
      strong.textContent = c.title;
      const small = document.createElement("small");
      small.textContent = `${fmtDateTime(c.updated_at)} · 메시지 ${c.message_count}개`;
      t.append(strong, small);
      const del = document.createElement("button");
      del.className = "link-btn danger";
      del.textContent = "삭제";
      del.title = "대화 삭제";
      del.addEventListener("click", (ev) => {
        ev.stopPropagation();
        deleteConversation(c.id);
      });
      li.append(t, del);
      li.addEventListener("click", () => openConversation(c.id));
      ul.appendChild(li);
    });
    highlightConversation();
  } catch (e) {
    $("convEmpty").hidden = false;
    $("convEmpty").textContent = `대화 목록을 불러오지 못했어요: ${e.message}`;
  }
}

async function openConversation(id) {
  try {
    const conv = await api(`/api/conversations/${id}`);
    state.conversationId = conv.id;
    $("chatTitle").textContent = conv.title;
    $("messages").querySelectorAll(".msg:not(.intro)").forEach((n) => n.remove());
    $("suggestions").hidden = true;
    conv.messages.forEach((m) => addMessage(m.role, m.content, m.tools_used));
    highlightConversation();
  } catch (e) {
    addMessage("error", `대화를 불러오지 못했어요: ${e.message}`);
  }
}

async function deleteConversation(id) {
  if (!confirm("이 대화를 삭제할까요?")) return;
  try {
    await api(`/api/conversations/${id}`, { method: "DELETE" });
    if (state.conversationId === id) resetChat();
    await loadConversations();
  } catch (e) {
    alert(`삭제하지 못했어요: ${e.message}`);
  }
}

// ---------- 데이터 관리 ----------
function setDataMsg(text, ok = true) {
  const el = $("dataMsg");
  el.textContent = text;
  el.className = "form-msg " + (ok ? "ok" : "err");
}

async function loadData(flashId) {
  try {
    state.data = await api("/api/data?order=desc");
    $("dataCount").textContent = `총 ${won.format(state.data.length)}개`;
    renderData(flashId);
  } catch (e) {
    setDataMsg(`데이터를 불러오지 못했어요: ${e.message}`, false);
  }
}

function renderData(flashId) {
  const tbody = $("dataBody");
  tbody.innerHTML = "";
  state.data.slice(0, state.shown).forEach((row) => tbody.appendChild(viewRow(row, row.id === flashId)));
  $("moreBtn").hidden = state.shown >= state.data.length;
}

function cell(text, cls) {
  const td = document.createElement("td");
  if (cls) td.className = cls;
  td.textContent = text;
  return td;
}

function viewRow(row, flash) {
  const tr = document.createElement("tr");
  if (flash) tr.className = "flash";
  const memo = cell(row.memo || "", "memo-cell");
  memo.title = row.memo || "";
  const actions = document.createElement("td");
  actions.className = "actions";
  const edit = document.createElement("button");
  edit.className = "link-btn";
  edit.textContent = "수정";
  edit.addEventListener("click", () => tr.replaceWith(editRow(row)));
  const del = document.createElement("button");
  del.className = "link-btn danger";
  del.textContent = "삭제";
  del.addEventListener("click", () => deleteData(row));
  actions.append(edit, del);
  tr.append(cell(row.date), cell(won.format(Math.round(row.value)), "num"), memo, actions);
  return tr;
}

function editRow(row) {
  const tr = document.createElement("tr");
  tr.className = "editing";
  const mk = (type, value, attrs = {}) => {
    const td = document.createElement("td");
    const input = document.createElement("input");
    input.type = type;
    input.value = value;
    Object.assign(input, attrs);
    td.appendChild(input);
    return [td, input];
  };
  const [tdDate, iDate] = mk("date", row.date);
  const [tdVal, iVal] = mk("number", Math.round(row.value), { min: 1, step: 1 });
  const [tdMemo, iMemo] = mk("text", row.memo || "", { maxLength: 200 });
  const actions = document.createElement("td");
  actions.className = "actions";
  const save = document.createElement("button");
  save.className = "link-btn";
  save.textContent = "저장";
  save.addEventListener("click", async () => {
    try {
      const updated = await api(`/api/data/${row.id}`, {
        method: "PUT",
        body: JSON.stringify({ date: iDate.value, value: Number(iVal.value), memo: iMemo.value }),
      });
      setDataMsg(`${updated.date} 데이터를 수정했어요.`);
      await refreshAll(updated.id);
    } catch (e) {
      setDataMsg(`수정 실패: ${e.message}`, false);
    }
  });
  const cancel = document.createElement("button");
  cancel.className = "link-btn";
  cancel.textContent = "취소";
  cancel.addEventListener("click", () => tr.replaceWith(viewRow(row)));
  actions.append(save, cancel);
  tr.append(tdDate, tdVal, tdMemo, actions);
  return tr;
}

async function deleteData(row) {
  if (!confirm(`${row.date} 데이터를 삭제할까요?`)) return;
  try {
    await api(`/api/data/${row.id}`, { method: "DELETE" });
    setDataMsg(`${row.date} 데이터를 삭제했어요.`);
    await refreshAll();
  } catch (e) {
    setDataMsg(`삭제 실패: ${e.message}`, false);
  }
}

async function addData(ev) {
  ev.preventDefault();
  const body = { date: $("addDate").value, value: Number($("addValue").value), memo: $("addMemo").value };
  try {
    const created = await api("/api/data", { method: "POST", body: JSON.stringify(body) });
    setDataMsg(`${created.date} 데이터를 추가했어요. 요약에도 반영됐어요.`);
    $("addForm").reset();
    $("addDate").value = new Date().toISOString().slice(0, 10);
    state.shown = Math.max(state.shown, PAGE);
    await refreshAll(created.id);
  } catch (e) {
    setDataMsg(`추가 실패: ${e.message}`, false);
  }
}

// ---------- 추가 통계 + 그래프 (보너스) ----------
function eok(v) {
  // 165000000 → "1.65억", 62000000 → "6,200만"
  if (v >= 1e8) return `${(v / 1e8).toFixed(v >= 1e9 ? 1 : 2)}억`;
  return `${won.format(Math.round(v / 1e4))}만`;
}

async function loadStatistics() {
  try {
    const st = await api("/api/data/statistics");
    state.series = st.series;
    $("stUp").textContent = st.up_ratio_pct == null ? "-" : `${st.up_ratio_pct}%`;
    $("stUpSub").textContent = `오른 날 ${st.up_days}일 · 내린 날 ${st.down_days}일`;
    const mdd = st.max_drawdown;
    $("stMdd").textContent = mdd ? `${mdd.pct.toFixed(1)}%` : "-";
    $("stMddSub").textContent = mdd ? `${mdd.peak_date} → ${mdd.trough_date}` : "";
    const last = st.monthly_returns[st.monthly_returns.length - 1];
    $("stMonth").textContent = last ? fmtPct(last.return_pct) : "-";
    $("stMonth").className = "value " + (last && last.return_pct > 0 ? "up" : last && last.return_pct < 0 ? "down" : "");
    $("stMonthSub").textContent = last ? `${last.month} 월초 대비` : "";
    drawChart();
  } catch (e) {
    $("chart").innerHTML = "";
    $("stUpSub").textContent = `통계를 불러오지 못했어요: ${e.message}`;
  }
}

function svgEl(tag, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

function drawChart() {
  const svg = $("chart");
  svg.innerHTML = "";
  const pts = state.range ? state.series.slice(-state.range) : state.series;
  if (pts.length < 2) return;
  // 화면 너비에 맞춰 좌표계를 정해 글자 크기가 늘어나거나 줄지 않게 한다
  const W = Math.max(300, Math.round(svg.clientWidth || 800));
  const H = W < 500 ? 200 : 260, L = 56, R = 10, T = 10, B = 26;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const vals = pts.flatMap((p) => [p.value, p.ma30].filter((v) => v != null));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || hi * 0.05;
  lo -= pad; hi += pad;
  const x = (i) => L + (i / (pts.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);

  // 가로 눈금 4개
  for (let k = 0; k <= 4; k++) {
    const v = lo + ((hi - lo) * k) / 4;
    svg.appendChild(svgEl("line", { class: "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    const t = svgEl("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" });
    t.textContent = eok(v);
    svg.appendChild(t);
  }
  // 날짜 눈금 (좁은 화면은 3개)
  const ticks = W < 500 ? 2 : 4;
  for (let k = 0; k <= ticks; k++) {
    const i = Math.round(((pts.length - 1) * k) / ticks);
    const t = svgEl("text", { x: x(i), y: H - 6, "text-anchor": k === 0 ? "start" : k === ticks ? "end" : "middle" });
    t.textContent = pts[i].date.slice(2).replace(/-/g, ".");
    svg.appendChild(t);
  }
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  svg.appendChild(svgEl("path", { class: "area", d: `${line}L${x(pts.length - 1)},${H - B}L${x(0)},${H - B}Z` }));
  const ma = pts.map((p, i) => (p.ma30 == null ? null : [x(i), y(p.ma30)])).filter(Boolean);
  if (ma.length > 1) svg.appendChild(svgEl("path", { class: "ma", d: ma.map((q, i) => `${i ? "L" : "M"}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join("") }));
  svg.appendChild(svgEl("path", { class: "price", d: line }));

  // 마우스를 올리면 그날 값 표시
  const cursor = svgEl("line", { class: "cursor", y1: T, y2: H - B, x1: -10, x2: -10 });
  const dot = svgEl("circle", { class: "dot", r: 4, cx: -10, cy: -10 });
  svg.append(cursor, dot);
  const tip = $("chartTip");
  const hit = svgEl("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
  svg.appendChild(hit);
  hit.addEventListener("mousemove", (ev) => {
    const box = svg.getBoundingClientRect();
    const sx = ((ev.clientX - box.left) / box.width) * W;
    const i = Math.max(0, Math.min(pts.length - 1, Math.round(((sx - L) / (W - L - R)) * (pts.length - 1))));
    const p = pts[i];
    cursor.setAttribute("x1", x(i)); cursor.setAttribute("x2", x(i));
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(p.value));
    tip.hidden = false;
    tip.textContent = `${p.date}  ${won.format(p.value)}원` + (p.ma30 ? ` (30일 평균 ${eok(p.ma30)})` : "");
    const px = (x(i) / W) * box.width;
    tip.style.left = `${Math.min(Math.max(px - 90, 0), Math.max(0, box.width - tip.offsetWidth))}px`;
  });
  hit.addEventListener("mouseleave", () => {
    tip.hidden = true;
    cursor.setAttribute("x1", -10); cursor.setAttribute("x2", -10);
    dot.setAttribute("cx", -10);
  });
}

// ---------- 다크 모드 (보너스) ----------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("themeBtn").textContent = theme === "dark" ? "☀️ 라이트" : "🌙 다크";
  try { localStorage.setItem("theme", theme); } catch (_) { /* 저장 불가 환경 무시 */ }
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (_) { /* 무시 */ }
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
  $("themeBtn").addEventListener("click", () =>
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
}

// 데이터가 바뀌면 목록·요약·통계를 함께 새로고침
function refreshAll(flashId) {
  return Promise.all([loadData(flashId), loadSummary(), loadStatistics(), loadSignal()]);
}

// ---------- 시작 ----------
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawChart, 150);
  });
  $("docsLink").href = API + "/docs";
  $("exportCsv").href = API + "/api/data/export?format=csv";
  $("exportJson").href = API + "/api/data/export?format=json";
  document.querySelectorAll(".range .chip").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(".range .chip").forEach((c) => c.classList.toggle("active", c === b));
      state.range = Number(b.dataset.range);
      drawChart();
    }));
  $("addDate").value = new Date().toISOString().slice(0, 10);
  $("chatForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    sendMessage($("chatInput").value);
  });
  $("suggestions").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => sendMessage(b.textContent)));
  $("newChatBtn").addEventListener("click", resetChat);
  $("sigAsk").addEventListener("click", () => {
    sendMessage("오늘 위험 단계가 왜 이렇게 나왔는지 뉴스와 함께 설명해 줘. 지금 팔아야 할까?");
    $("chatInput").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("addForm").addEventListener("submit", addData);
  $("moreBtn").addEventListener("click", () => {
    state.shown += PAGE;
    renderData();
  });

  if (await waitForServer()) {
    await Promise.all([loadSummary(), loadConversations(), loadData(), loadStatistics(), loadSignal(), loadNews(), loadAlerts()]);
  }
});

// 바닐라 JS 프론트엔드. API 주소는 config.js 의 window.API_BASE_URL 에서 읽는다.
const API = (window.API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const PAGE = 30;

const $ = (id) => document.getElementById(id);
const won = new Intl.NumberFormat("ko-KR");
const state = { conversationId: null, data: [], shown: PAGE, sending: false };

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

// ---------- 채팅 ----------
function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text; // textContent 로 넣어 HTML 주입을 막는다
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
    addMessage("assistant", res.reply);
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
    conv.messages.forEach((m) => addMessage(m.role, m.content));
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
      await Promise.all([loadData(updated.id), loadSummary()]);
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
    await Promise.all([loadData(), loadSummary()]);
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
    await Promise.all([loadData(created.id), loadSummary()]);
  } catch (e) {
    setDataMsg(`추가 실패: ${e.message}`, false);
  }
}

// ---------- 시작 ----------
document.addEventListener("DOMContentLoaded", async () => {
  $("docsLink").href = API + "/docs";
  $("addDate").value = new Date().toISOString().slice(0, 10);
  $("chatForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    sendMessage($("chatInput").value);
  });
  $("suggestions").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => sendMessage(b.textContent)));
  $("newChatBtn").addEventListener("click", resetChat);
  $("addForm").addEventListener("submit", addData);
  $("moreBtn").addEventListener("click", () => {
    state.shown += PAGE;
    renderData();
  });

  if (await waitForServer()) {
    await Promise.all([loadSummary(), loadConversations(), loadData()]);
  }
});

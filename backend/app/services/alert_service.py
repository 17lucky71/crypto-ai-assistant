"""디스코드 위험 알림: 매일 한 번 실행 → 최신 시세 반영 → 위험 단계 계산 → 조건에 맞으면 사유와 함께 전송.

실행 주체: GitHub Actions 스케줄(.github/workflows/daily-alert.yml)이 POST /api/alerts/run 을 호출한다.
ALERT_MODE
  risk (기본) : 위험 단계가 '주의' 이상으로 새로 올라가거나 더 높아지면 🔴 경고, '관심' 이하로 내려오면 ✅ 해제
  change      : 위험 단계가 바뀔 때마다
  daily       : 매일
메시지의 제목을 누르면 대시보드(FRONTEND_URL#risk)로 바로 들어간다.
"""
import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from ..config import settings
from ..db import store
from . import chat_service, market_service, news_service, signal_service

logger = logging.getLogger(__name__)

ALERT_COLLECTION = "alerts"
STATE_ID = "state"
SEND_RETRIES = 3  # 디스코드 전송 재시도 횟수
ALERT_STEP = 2  # '주의' 단계부터 경고
LEVEL_STYLE = {  # 단계별 아이콘과 색 (대시보드와 같은 색)
    0: ("🟢", 0x2E8B57), 1: ("🔵", 0x2F6FDE), 2: ("🟡", 0xE3A008), 3: ("🟠", 0xEA6A0A), 4: ("🔴", 0xCF1F3A),
}


# 디스코드(Cloudflare)는 브라우저나 봇이 아닌 User-Agent 를 막는 경우가 있어 봇 형식으로 보낸다
DISCORD_UA = "DiscordBot (https://github.com/17lucky71/crypto-ai-assistant, 1.0)"


class DiscordSendError(OSError):
    """디스코드가 요청을 거절했을 때 (이유 포함)."""


class AlertConfigError(Exception):
    """웹훅 주소가 없을 때."""


def _won(v: float) -> str:
    v = round(v)
    eok, man = divmod(v // 10000, 10000)
    return f"{eok}억 {man:,}만 원" if eok else f"{man:,}만 원"


def _ai_comment(sig: dict, news: dict) -> str | None:
    """뉴스 제목과 신호 근거를 보고 AI 가 2문장으로 해석. 실패하면 생략."""
    if not settings.OPENAI_API_KEY or not news.get("items"):
        return None
    headlines = "\n".join(f"- {n['published']} {n['title']} ({n['source']})" for n in news["items"][:8])
    reasons = "\n".join(f"- {r['text']}" for r in sig["reasons"])
    prompt = (f"비트코인 규칙 기반 신호: {sig['label']}\n근거:\n{reasons}\n\n최근 뉴스 제목:\n{headlines}\n\n"
              "위 뉴스 중 이 신호와 관련 있어 보이는 흐름을 한국어 2문장으로 설명하세요. "
              "뉴스에 없는 사실은 지어내지 말고, '반드시 오른다/내린다' 같은 단정은 쓰지 마세요.")
    try:
        msg = chat_service._complete([{"role": "user", "content": prompt}], use_tools=False)
        return (msg.content or "").strip()[:600] or None
    except Exception:
        logger.warning("AI 해석 생성 실패 (알림은 계속 보냄)")
        return None


def _dashboard_url() -> str:
    return settings.FRONTEND_URL.rstrip("/") + "/#risk"


def build_message(sig: dict, news: dict, comment: str | None, kind: str = "risk") -> dict:
    """kind: risk(위험 경고) / release(위험 해제) / report(정기 보고)."""
    lv = sig["level"]
    icon, color = LEVEL_STYLE[lv["step"]]
    minus = [r for r in sig["reasons"] if r["score"] < 0]
    plus = [r for r in sig["reasons"] if r["score"] > 0]

    if kind == "hello":
        headline = f"✅ 비트코인 위험 알리미가 연결됐어요 — 지금은 '{lv['name']}' 단계예요"
        desc = (f"{lv['desc']}\n\n**지금 보이는 근거**\n" + "\n".join(f"• {r['text']}" for r in sig["reasons"])
                + "\n\n위험 단계가 '주의' 이상으로 올라가면 이 채널로 이유와 함께 알려 드릴게요.")
    elif kind == "release":
        headline = f"✅ 위험 해제 — 지금은 '{lv['name']}' 단계예요"
        desc = "하락 근거가 줄어들어 경고를 해제해요.\n\n**지금 보이는 근거**\n" + "\n".join(f"• {r['text']}" for r in sig["reasons"])
    else:
        headline = f"{icon} 위험 단계 '{lv['name']}' — {sig['label']}"
        desc = f"{lv['desc']}\n\n**팔아야 할 이유**\n" + ("\n".join(f"• {r['text']}" for r in minus) or "• 뚜렷한 하락 근거 없음")
        if plus:
            desc += "\n\n**버틸 이유 (반대 근거)**\n" + "\n".join(f"• {r['text']}" for r in plus)
    if comment:
        desc += f"\n\n**🤖 뉴스로 본 해석**\n{comment}"
    desc += f"\n\n📊 [대시보드에서 자세히 보기]({_dashboard_url()})"

    bt = sig["backtest"]
    sell = bt["sell"]
    fields = [
        {"name": "현재가", "value": f"{_won(sig['price'])}\n({sig['date']} 종가)", "inline": True},
        {"name": f"{sig['forecast']['horizon_days']}일 예상 범위", "value": f"{_won(sig['forecast']['low'])} ~\n{_won(sig['forecast']['high'])}", "inline": True},
        {"name": "매도 신호 성적표",
         "value": (f"적중률 {sell['hit_rate_pct']}% ({sell['count']}회)\n신호 뒤 7일 평균 {bt['after_sell_avg_pct']:+.2f}%\n(평소 {bt['all_days_avg_pct']:+.2f}%)"
                   if sell["count"] else "아직 표본 없음"), "inline": True},
    ]
    items = news.get("items", [])[:3]
    if items:
        fields.append({"name": "📰 최근 뉴스", "value": "\n".join(f"[{n['title'][:70]}]({n['link']})" for n in items)[:1000]})
    return {
        "username": "비트코인 위험 알리미",
        # @everyone 을 붙이면 채널 알림 설정이 '@멘션만'이어도 휴대폰이 울린다
        "content": (f"{settings.DISCORD_MENTION} " if settings.DISCORD_MENTION else "") + headline,
        "allowed_mentions": {"parse": ["everyone"] if settings.DISCORD_MENTION else []},
        "embeds": [{
            "title": f"{icon} 비트코인 위험 단계: {lv['name']} ({sig['date']})",
            "url": _dashboard_url(),
            "description": desc[:3800],
            "color": 0x2E8B57 if kind in ("release", "hello") else color,
            "fields": fields,
            "footer": {"text": sig["disclaimer"]},
        }],
    }


def send_discord(payload: dict) -> None:
    if not settings.DISCORD_WEBHOOK_URL:
        raise AlertConfigError("DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, SEND_RETRIES + 1):  # 일시적 오류(네트워크·429·5xx)는 잠깐 쉬었다가 다시 보낸다
        req = urllib.request.Request(settings.DISCORD_WEBHOOK_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": DISCORD_UA})
        try:
            with urllib.request.urlopen(req, timeout=10):
                return
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                # 주소가 틀린 경우(404 등)는 다시 보내도 소용없다. 디스코드가 알려 준 이유를 함께 남긴다.
                try:
                    reason = e.read()[:300].decode("utf-8", "replace")
                except Exception:
                    reason = ""
                raise DiscordSendError(f"디스코드가 HTTP {e.code} 로 거절했습니다. {reason}".strip()) from e
            last_error = e
        except urllib.error.URLError as e:
            last_error = e
        logger.warning("디스코드 전송 실패 (%d/%d회): %s", attempt, SEND_RETRIES, last_error)
        time.sleep(2 * attempt)
    raise last_error  # 끝내 실패하면 API 가 502 를 돌려주고, GitHub Actions 실행이 '실패'로 표시된다


def _decide_kind(step: int, last_step: int | None, force: bool) -> str | None:
    """보낼 메시지 종류를 정한다. None 이면 보내지 않는다."""
    mode = settings.ALERT_MODE
    if mode == "daily" or force:
        return "risk" if step >= ALERT_STEP else "report"
    if mode == "change":
        return None if step == last_step else ("risk" if step >= ALERT_STEP else "report")
    # risk 모드 (기본)
    prev = last_step if last_step is not None else 0
    if step >= ALERT_STEP and step > prev:
        return "risk"  # 위험이 새로 생기거나 더 높아짐
    if prev >= ALERT_STEP and step < ALERT_STEP:
        return "release"  # 위험이 풀림
    return None


def run(force: bool = False) -> dict:
    """매일 실행: 시세 갱신 → 위험 단계 계산 → 조건에 맞으면 전송 → 상태 저장."""
    update = market_service.update_latest()
    sig = signal_service.current_signal()
    if not sig.get("available"):
        return {"sent": False, "reason": sig.get("message"), "update": update}

    if not settings.DISCORD_WEBHOOK_URL:
        # 웹훅이 없으면 상태를 저장하지 않는다 (연결 후 첫 실행에 '연결 완료' 메시지를 보내기 위해)
        return {"sent": False, "reason": "DISCORD_WEBHOOK_URL 이 설정되지 않았습니다.", "update": update}

    state = store.get(ALERT_COLLECTION, STATE_ID) or {}
    step = sig["level"]["step"]
    last_step = state.get("last_step")
    kind = "hello" if not state else _decide_kind(step, last_step, force)
    result = {"sent": False, "kind": kind, "level": sig["level"]["name"], "step": step, "previous_step": last_step,
              "signal": sig["signal"], "date": sig["date"], "update": update}
    if kind:
        news = news_service.recent_news()
        send_discord(build_message(sig, news, _ai_comment(sig, news) if kind in ("risk", "report") else None, kind))
        result["sent"] = True

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.add(ALERT_COLLECTION, {"last_step": step, "last_signal": sig["signal"], "last_date": sig["date"], "updated_at": now},
              doc_id=STATE_ID)
    if result["sent"]:
        store.add(ALERT_COLLECTION, {"type": "sent", "kind": kind, "level": sig["level"]["name"], "step": step,
                                     "signal": sig["signal"], "date": sig["date"], "score": sig["score"], "price": sig["price"],
                                     "sent_at": now})
    return result


def history(limit: int = 10) -> list[dict]:
    """디스코드로 보낸 기록 (최신순)."""
    rows = [d for d in store.list(ALERT_COLLECTION) if d.get("type") == "sent"]
    rows.sort(key=lambda d: d.get("sent_at", ""), reverse=True)
    return [{k: d.get(k) for k in ("kind", "level", "step", "signal", "date", "score", "price", "sent_at")} for d in rows[:limit]]

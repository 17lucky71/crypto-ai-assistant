"""디스코드 알림: 매일 한 번 실행 → 최신 시세 반영 → 신호 계산 → (바뀌었으면) 디스코드로 사유와 함께 전송.

실행 주체: GitHub Actions 스케줄(.github/workflows/daily-alert.yml)이 POST /api/alerts/run 을 호출한다.
ALERT_MODE=change(기본) 이면 신호가 바뀐 날만, daily 면 매일 보낸다.
"""
import json
import logging
import urllib.request
from datetime import datetime, timezone

from ..config import settings
from ..db import store
from . import chat_service, market_service, news_service, signal_service

logger = logging.getLogger(__name__)

ALERT_COLLECTION = "alerts"
STATE_ID = "state"
COLORS = {"BUY": 0x16A34A, "SELL": 0xDC2626, "HOLD": 0x6B7280}
ICONS = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}
WHY = {"BUY": "사야 할 이유", "SELL": "팔아야 할 이유", "HOLD": "지켜봐야 할 이유"}


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


def build_message(sig: dict, news: dict, comment: str | None) -> dict:
    s = sig["signal"]
    sign = {"BUY": 1, "SELL": -1}.get(s, 0)
    main = [r for r in sig["reasons"] if (r["score"] == sign if sign else r["score"] != 0)] or sig["reasons"]
    counter = [r for r in sig["reasons"] if sign and r["score"] == -sign]
    desc = f"**{WHY[s]}**\n" + "\n".join(f"• {r['text']}" for r in main)
    if counter:
        desc += "\n\n**반대 근거**\n" + "\n".join(f"• {r['text']}" for r in counter)
    if comment:
        desc += f"\n\n**🤖 뉴스로 본 해석**\n{comment}"

    bt = sig["backtest"]
    rate = sig["this_signal_hit_rate_pct"]
    key = s.lower()
    fields = [
        {"name": "현재가", "value": f"{_won(sig['price'])}\n({sig['date']} 종가)", "inline": True},
        {"name": f"{sig['forecast']['horizon_days']}일 예상 범위", "value": f"{_won(sig['forecast']['low'])} ~\n{_won(sig['forecast']['high'])}", "inline": True},
        {"name": "이 신호의 과거 적중률",
         "value": f"{rate}% ({bt[key]['count']}회)" if rate is not None else "표본 없음", "inline": True},
    ]
    items = news.get("items", [])[:3]
    if items:
        fields.append({"name": "📰 최근 뉴스", "value": "\n".join(f"[{n['title'][:70]}]({n['link']})" for n in items)[:1000]})
    return {
        "username": "비트코인 AI 비서",
        "content": f"{ICONS[s]} **비트코인 {sig['label']}** — 점수 {sig['score']:+d}",
        "embeds": [{
            "title": f"{ICONS[s]} {sig['label']} ({sig['date']})",
            "description": desc[:3800],
            "color": COLORS[s],
            "fields": fields,
            "footer": {"text": sig["disclaimer"]},
        }],
    }


def send_discord(payload: dict) -> None:
    if not settings.DISCORD_WEBHOOK_URL:
        raise AlertConfigError("DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    req = urllib.request.Request(settings.DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "crypto-ai-assistant"})
    with urllib.request.urlopen(req, timeout=10):
        pass


def run(force: bool = False) -> dict:
    """매일 실행: 시세 갱신 → 신호 계산 → 조건에 맞으면 전송 → 상태 저장."""
    update = market_service.update_latest()
    sig = signal_service.current_signal()
    if not sig.get("available"):
        return {"sent": False, "reason": sig.get("message"), "update": update}

    state = store.get(ALERT_COLLECTION, STATE_ID) or {}
    changed = state.get("last_signal") != sig["signal"]
    should_send = force or settings.ALERT_MODE == "daily" or changed
    result = {"sent": False, "signal": sig["signal"], "label": sig["label"], "date": sig["date"],
              "previous": state.get("last_signal"), "changed": changed, "update": update}
    if should_send:
        news = news_service.recent_news()
        send_discord(build_message(sig, news, _ai_comment(sig, news)))
        result["sent"] = True

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    store.add(ALERT_COLLECTION, {"last_signal": sig["signal"], "last_date": sig["date"], "updated_at": now}, doc_id=STATE_ID)
    if result["sent"]:
        store.add(ALERT_COLLECTION, {"type": "sent", "signal": sig["signal"], "date": sig["date"], "score": sig["score"], "sent_at": now})
    return result

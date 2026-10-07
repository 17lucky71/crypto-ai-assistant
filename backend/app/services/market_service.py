"""업비트에서 최근 일봉을 받아 빠진 날짜만 Firestore 에 추가한다 (매일 알림 실행 전에 호출).

오늘(KST) 캔들은 아직 마감 전이라 저장하지 않는다.
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

from . import data_service

API = "https://api.upbit.com/v1/candles/days?market=KRW-BTC&count={count}"
BIG_MOVE_PCT = 5.0
KST = timezone(timedelta(hours=9))


def fetch_recent(count: int = 30) -> list[dict]:
    req = urllib.request.Request(API.format(count=count), headers={"Accept": "application/json", "User-Agent": "crypto-ai-assistant"})
    with urllib.request.urlopen(req, timeout=10) as res:
        candles = json.loads(res.read().decode("utf-8"))
    today = datetime.now(KST).date().isoformat()
    rows = {c["candle_date_time_kst"][:10]: float(c["trade_price"]) for c in candles}
    return [{"date": d, "value": v} for d, v in sorted(rows.items()) if d < today]


def update_latest() -> dict:
    """새 날짜만 추가하고, 추가한 날짜 목록을 돌려준다."""
    try:
        recent = fetch_recent()
    except Exception as e:
        return {"added": [], "error": f"업비트 시세를 가져오지 못했습니다: {e.__class__.__name__}"}
    existing = {r["date"]: r["value"] for r in data_service.list_data()}
    added = []
    for r in recent:
        if r["date"] in existing:
            continue
        prev_dates = [d for d in existing if d < r["date"]]
        memo = ""
        if prev_dates:
            prev = existing[max(prev_dates)]
            pct = (r["value"] - prev) / prev * 100
            if abs(pct) >= BIG_MOVE_PCT:
                memo = f"일간 {pct:+.1f}% {'급등' if pct > 0 else '급락'}"
        data_service.create_data(datetime.fromisoformat(r["date"]).date(), r["value"], memo)
        existing[r["date"]] = r["value"]
        added.append(r["date"])
    return {"added": added}

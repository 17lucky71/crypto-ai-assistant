"""데이터 CRUD 와 요약 계산. 라우터는 이 함수들만 호출한다."""
from collections import defaultdict
from datetime import date as Date, datetime, timezone
from statistics import mean, pstdev

from ..config import settings
from ..db import DATA_COLLECTION, store

_summary_cache: dict | None = None  # 데이터가 바뀌면 비운다


def _invalidate() -> None:
    global _summary_cache
    _summary_cache = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_item(doc: dict) -> dict:
    return {"id": doc["id"], "date": doc["date"], "value": float(doc["value"]), "memo": doc.get("memo", "")}


def list_data() -> list[dict]:
    """날짜 오름차순 목록."""
    return sorted((_to_item(d) for d in store.list(DATA_COLLECTION)), key=lambda x: x["date"])


def get_data(doc_id: str) -> dict | None:
    doc = store.get(DATA_COLLECTION, doc_id)
    return _to_item(doc) if doc else None


def find_by_date(day: Date) -> dict | None:
    key = day.isoformat()
    return next((d for d in list_data() if d["date"] == key), None)


def create_data(day: Date, value: float, memo: str) -> dict:
    now = _now()
    doc = {"date": day.isoformat(), "value": value, "memo": memo, "created_at": now, "updated_at": now}
    doc_id = store.add(DATA_COLLECTION, doc)
    _invalidate()
    return {"id": doc_id, **_to_item({"id": doc_id, **doc})}


def update_data(doc_id: str, changes: dict) -> dict:
    if "date" in changes and isinstance(changes["date"], Date):
        changes["date"] = changes["date"].isoformat()
    changes["updated_at"] = _now()
    store.update(DATA_COLLECTION, doc_id, changes)
    _invalidate()
    return get_data(doc_id)


def delete_data(doc_id: str) -> None:
    store.delete(DATA_COLLECTION, doc_id)
    _invalidate()


# ---------------- 요약 ----------------
def _pct(a: float, b: float) -> float:
    return round((b - a) / a * 100, 2) if a else 0.0


def _trend_label(values: list[float]) -> str:
    """최근 30일 평균을 그 전 30일 평균과 비교해 상승/하락/보합을 정한다."""
    if len(values) < 14:
        return "판단 불가 (데이터 부족)"
    window = 30 if len(values) >= 60 else len(values) // 2
    recent, before = mean(values[-window:]), mean(values[-2 * window:-window])
    change = _pct(before, recent)
    if change >= 3:
        label = "상승"
    elif change <= -3:
        label = "하락"
    else:
        label = "보합"
    return f"{label} (최근 {window}일 평균이 직전 {window}일 대비 {change:+.1f}%)"


def build_summary() -> dict:
    global _summary_cache
    if _summary_cache is not None:
        return _summary_cache

    rows = list_data()
    base = {"name": settings.DATA_NAME, "unit": settings.DATA_UNIT}
    if not rows:
        _summary_cache = {**base, "period": "데이터 없음", "count": 0, "metrics": {}, "trend": "판단 불가 (데이터 없음)",
                          "recent": [], "monthly": [], "notable": []}
        return _summary_cache

    values = [r["value"] for r in rows]
    hi = max(rows, key=lambda r: r["value"])
    lo = min(rows, key=lambda r: r["value"])
    returns = [_pct(values[i - 1], values[i]) for i in range(1, len(values))]

    metrics = {
        "latest": {"date": rows[-1]["date"], "value": round(values[-1])},
        "average": round(mean(values)),
        "max": {"date": hi["date"], "value": round(hi["value"])},
        "min": {"date": lo["date"], "value": round(lo["value"])},
        "period_change_pct": _pct(values[0], values[-1]),
        "change_30d_pct": _pct(values[-31], values[-1]) if len(values) > 30 else None,
        "daily_volatility_pct": round(pstdev(returns), 2) if len(returns) > 1 else None,
        "biggest_rise": max(({"date": rows[i + 1]["date"], "pct": r} for i, r in enumerate(returns)), key=lambda x: x["pct"], default=None),
        "biggest_drop": min(({"date": rows[i + 1]["date"], "pct": r} for i, r in enumerate(returns)), key=lambda x: x["pct"], default=None),
    }

    by_month: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_month[r["date"][:7]].append(r["value"])
    monthly = [{"month": m, "avg": round(mean(v)), "max": round(max(v)), "min": round(min(v)), "days": len(v)}
               for m, v in sorted(by_month.items())]

    _summary_cache = {
        **base,
        "period": f"{rows[0]['date']} ~ {rows[-1]['date']}",
        "count": len(rows),
        "metrics": metrics,
        "trend": _trend_label(values),
        "recent": [{"date": r["date"], "value": round(r["value"])} for r in rows[-14:]],
        "monthly": monthly[-24:],
        "notable": [{"date": r["date"], "memo": r["memo"]} for r in rows if r["memo"]][-20:],
    }
    return _summary_cache

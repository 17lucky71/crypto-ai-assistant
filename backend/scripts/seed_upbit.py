"""업비트 KRW-BTC 일봉을 받아 CSV 로 저장하고, 요약을 출력하고, Firestore 에 올린다.

사용법 (backend 폴더에서, venv 활성화 후)
  python scripts/seed_upbit.py                 # 400일 받아 data/btc_daily.csv 저장 + 요약 출력
  python scripts/seed_upbit.py --days 500      # 받을 일수 변경
  python scripts/seed_upbit.py --upload        # 받은 뒤 Firestore 'data' 컬렉션에 업로드
  python scripts/seed_upbit.py --from-csv --upload   # 이미 받은 CSV 로 업로드만

- 업비트 시세 API 는 키 없이 쓸 수 있다.
- 하루 등락이 ±5% 이상인 날은 memo 에 "일간 +6.3% 급등"처럼 자동으로 적는다.
- 이미 Firestore 에 있는 날짜는 건너뛴다 (여러 번 실행해도 중복되지 않음).
"""
import argparse
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "btc_daily.csv"
API = "https://api.upbit.com/v1/candles/days"
BIG_MOVE_PCT = 5.0


def fetch_days(days: int, market: str = "KRW-BTC") -> list[dict]:
    """업비트는 한 번에 최대 200개라 'to' 를 옮겨 가며 여러 번 받는다."""
    rows: dict[str, float] = {}
    to = None
    while len(rows) < days:
        count = min(200, days - len(rows))
        url = f"{API}?market={market}&count={count}" + (f"&to={to}" if to else "")
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "crypto-ai-assistant"})
        with urllib.request.urlopen(req, timeout=15) as res:
            candles = json.loads(res.read().decode("utf-8"))
        if not candles:
            break
        for c in candles:
            rows[c["candle_date_time_kst"][:10]] = float(c["trade_price"])  # 종가
        oldest = min(c["candle_date_time_utc"] for c in candles)
        to = (datetime.fromisoformat(oldest)).strftime("%Y-%m-%dT%H:%M:%S")
        time.sleep(0.2)  # 요청 제한 배려
    ordered = sorted(rows.items())[-days:]
    return [{"date": d, "value": v} for d, v in ordered]


def add_memos(rows: list[dict]) -> list[dict]:
    for i, r in enumerate(rows):
        r["memo"] = ""
        if i == 0:
            continue
        pct = (r["value"] - rows[i - 1]["value"]) / rows[i - 1]["value"] * 100
        if abs(pct) >= BIG_MOVE_PCT:
            r["memo"] = f"일간 {pct:+.1f}% {'급등' if pct > 0 else '급락'}"
    return rows


def save_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "value", "memo"])
        w.writeheader()
        w.writerows(rows)


def load_csv() -> list[dict]:
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return [{"date": r["date"], "value": float(r["value"]), "memo": r.get("memo", "")} for r in csv.DictReader(f)]


def check_and_summarize(rows: list[dict]) -> None:
    """간단한 정제 점검과 요약 통계 출력 (데이터 분석 단계)."""
    dates = [datetime.fromisoformat(r["date"]).date() for r in rows]
    expected = (dates[-1] - dates[0]).days + 1
    missing = sorted(set(dates[0] + timedelta(i) for i in range(expected)) - set(dates))
    values = [r["value"] for r in rows]
    returns = [(values[i] - values[i - 1]) / values[i - 1] * 100 for i in range(1, len(values))]
    hi, lo = max(rows, key=lambda r: r["value"]), min(rows, key=lambda r: r["value"])

    print("=" * 60)
    print(f"기간      : {rows[0]['date']} ~ {rows[-1]['date']}")
    print(f"개수      : {len(rows)}일 (빠진 날짜 {len(missing)}개, 0 이하 값 {sum(v <= 0 for v in values)}개)")
    print(f"평균      : {mean(values):,.0f} 원")
    print(f"최고      : {hi['value']:,.0f} 원 ({hi['date']})")
    print(f"최저      : {lo['value']:,.0f} 원 ({lo['date']})")
    print(f"기간 변화 : {(values[-1] - values[0]) / values[0] * 100:+.1f}%")
    print(f"일간 변동성(표준편차): {pstdev(returns):.2f}%")
    print(f"±{BIG_MOVE_PCT:.0f}% 이상 급변일: {sum(1 for r in rows if r['memo'])}일")
    if len(values) >= 60:
        recent, before = mean(values[-30:]), mean(values[-60:-30])
        print(f"최근 30일 평균 vs 직전 30일: {(recent - before) / before * 100:+.1f}%")
    print("=" * 60)


def upload(rows: list[dict]) -> None:
    sys.path.insert(0, str(ROOT))
    from app.db import DATA_COLLECTION, STORE_KIND, store  # noqa: E402

    if STORE_KIND != "firestore":
        print("Firebase 키가 설정되지 않아 업로드할 수 없습니다. .env 의 FIREBASE_SERVICE_ACCOUNT_PATH 를 확인하세요.")
        return
    existing = {d["date"] for d in store.list(DATA_COLLECTION)}
    todo = [r for r in rows if r["date"] not in existing]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    client = store.client
    for start in range(0, len(todo), 400):  # Firestore 배치는 최대 500건
        batch = client.batch()
        for r in todo[start:start + 400]:
            batch.set(client.collection(DATA_COLLECTION).document(), {**r, "created_at": now, "updated_at": now})
        batch.commit()
    print(f"업로드 완료: 새로 {len(todo)}건, 이미 있던 {len(rows) - len(todo)}건은 건너뜀")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=400)
    p.add_argument("--upload", action="store_true")
    p.add_argument("--from-csv", action="store_true")
    args = p.parse_args()

    if args.from_csv:
        rows = load_csv()
    else:
        rows = add_memos(fetch_days(args.days))
        save_csv(rows)
        print(f"저장: {CSV_PATH}")
    check_and_summarize(rows)
    if args.upload:
        upload(rows)


if __name__ == "__main__":
    main()

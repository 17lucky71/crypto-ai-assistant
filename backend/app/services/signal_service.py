"""매매 신호 · 7일 예상 범위 · 과거 적중률(백테스트).

규칙 기반이라 '왜 그 신호인지' 근거를 문장으로 함께 돌려준다.
예측을 맹신하지 않도록, 같은 규칙을 과거 데이터에 적용했을 때의 적중률도 계산해 함께 보여 준다.

신호 규칙 (각 항목이 +1 매수 쪽 / -1 매도 쪽 / 0 중립 으로 투표)
  1. 추세    : 7일 이동평균이 30일 이동평균보다 위(+1) / 아래(-1)
  2. RSI(14) : 30 이하 과매도(+1) / 70 이상 과열(-1)
  3. 14일 모멘텀 : +7% 이상(+1) / -7% 이하(-1)
  4. 고점 대비 : 최근 90일 고점보다 15% 이상 낮음(-1)
  5. 30일선 거리 : 30일 평균보다 3% 이상 위(+1) / 3% 이상 아래(-1)
  합계 >= +2 → 매수 신호, <= -2 → 매도 신호, 그 사이 → 관망
"""
from math import sqrt
from statistics import mean, pstdev

from . import data_service

HORIZON = 7  # 며칠 뒤를 보는 예측인지
MIN_DAYS = 90  # 지표 계산에 필요한 최소 일수
LABELS = {"BUY": "매수 신호", "SELL": "매도 신호", "HOLD": "관망"}

# 위험 단계: 국가 위기경보(관심·주의·경계·심각)와 같은 이름을 써서 누구나 바로 알아보게 한다
LEVELS = [
    {"step": 0, "key": "safe", "name": "안전", "desc": "뚜렷한 하락 근거가 없어요."},
    {"step": 1, "key": "watch", "name": "관심", "desc": "하락 근거가 하나 보여요. 흐름을 지켜보세요."},
    {"step": 2, "key": "caution", "name": "주의", "desc": "하락 근거가 겹치기 시작했어요. 매도를 고민해 볼 때예요."},
    {"step": 3, "key": "warning", "name": "경계", "desc": "하락 근거가 여럿 겹쳤어요. 매도를 검토할 시점이에요."},
    {"step": 4, "key": "severe", "name": "심각", "desc": "거의 모든 지표가 하락을 가리켜요. 손실을 줄일 준비를 하세요."},
]


def level_for(score: int) -> dict:
    """점수 → 위험 단계. 0 이상 안전, -1 관심, -2 주의(매도 신호 시작), -3 경계, -4 이하 심각."""
    if score >= 0:
        return LEVELS[0]
    return LEVELS[min(-score, 4)]


def _rsi(values: list[float], period: int = 14) -> float:
    diffs = [values[i] - values[i - 1] for i in range(len(values) - period, len(values))]
    gain = sum(d for d in diffs if d > 0) / period
    loss = sum(-d for d in diffs if d < 0) / period
    if loss == 0:
        return 100.0
    return 100 - 100 / (1 + gain / loss)


def indicators(values: list[float]) -> dict:
    """마지막 날 기준 지표들. values 는 날짜 오름차순 종가."""
    price = values[-1]
    ma7, ma30 = mean(values[-7:]), mean(values[-30:])
    high90 = max(values[-90:])
    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(len(values) - 30, len(values))]
    return {
        "price": price,
        "ma7": ma7,
        "ma30": ma30,
        "rsi14": _rsi(values),
        "momentum14_pct": (price - values[-15]) / values[-15] * 100,
        "from_high90_pct": (price - high90) / high90 * 100,
        "vs_ma30_pct": (price - ma30) / ma30 * 100,
        "daily_vol_pct": pstdev(returns) * 100,
    }


def _vote(ind: dict) -> tuple[int, list[dict]]:
    """규칙별 점수와 근거 문장."""
    reasons: list[dict] = []

    def add(score: int, text: str) -> None:
        reasons.append({"score": score, "text": text})

    gap = (ind["ma7"] - ind["ma30"]) / ind["ma30"] * 100
    if ind["ma7"] < ind["ma30"]:
        add(-1, f"단기 추세 하락: 7일 평균이 30일 평균보다 {abs(gap):.1f}% 아래")
    else:
        add(+1, f"단기 추세 상승: 7일 평균이 30일 평균보다 {gap:.1f}% 위")

    r = ind["rsi14"]
    if r >= 70:
        add(-1, f"과열: RSI {r:.0f} (70 이상이면 단기 과매수로 봄)")
    elif r <= 30:
        add(+1, f"과매도: RSI {r:.0f} (30 이하면 반등 가능 구간으로 봄)")
    else:
        add(0, f"RSI {r:.0f}로 중립 구간(30~70)")

    m = ind["momentum14_pct"]
    if m >= 7:
        add(+1, f"상승 탄력: 최근 14일 {m:+.1f}%")
    elif m <= -7:
        add(-1, f"하락 탄력: 최근 14일 {m:+.1f}%")
    else:
        add(0, f"최근 14일 {m:+.1f}%로 큰 방향성 없음")

    h = ind["from_high90_pct"]
    if h <= -15:
        add(-1, f"약세장: 최근 90일 고점보다 {abs(h):.1f}% 낮음")

    v = ind["vs_ma30_pct"]
    if v >= 3:
        add(+1, f"가격이 30일 평균보다 {v:.1f}% 위")
    elif v <= -3:
        add(-1, f"가격이 30일 평균보다 {abs(v):.1f}% 아래")

    return sum(x["score"] for x in reasons), reasons


def _decide(score: int) -> str:
    if score >= 2:
        return "BUY"
    if score <= -2:
        return "SELL"
    return "HOLD"


def backtest(values: list[float]) -> dict:
    """같은 규칙을 과거 날짜마다 적용하고, HORIZON 일 뒤 실제 방향과 비교한다 (미래 데이터는 쓰지 않음)."""
    stats = {"BUY": [0, 0], "SELL": [0, 0], "HOLD": [0, 0]}  # [맞음, 전체]
    up_days = total = 0
    all_returns: list[float] = []
    sell_returns: list[float] = []
    sell_worst: list[float] = []  # 매도 신호 뒤 7일 안에 가장 많이 떨어졌던 폭
    for i in range(MIN_DAYS, len(values) - HORIZON):
        past = values[: i + 1]
        signal = _decide(_vote(indicators(past))[0])
        future = (values[i + HORIZON] - values[i]) / values[i]
        total += 1
        up_days += future > 0
        hit = (signal == "BUY" and future > 0) or (signal == "SELL" and future < 0) or (signal == "HOLD" and abs(future) < 0.03)
        stats[signal][0] += hit
        stats[signal][1] += 1
        all_returns.append(future)
        if signal == "SELL":
            sell_returns.append(future)
            sell_worst.append(min(values[i + 1: i + HORIZON + 1]) / values[i] - 1)

    def rate(k: str):
        hit, n = stats[k]
        return {"count": n, "hit_rate_pct": round(hit / n * 100, 1) if n else None}

    return {
        "horizon_days": HORIZON,
        "tested_days": total,
        "buy": rate("BUY"),
        "sell": rate("SELL"),
        "hold": rate("HOLD"),
        "baseline_up_pct": round(up_days / total * 100, 1) if total else None,
        # 매도 신호의 비교 기준: 아무 신호 없이 '내린다'고만 했을 때의 적중률 (7일 뒤 오르지 않은 날의 비율)
        "baseline_down_pct": round((total - up_days) / total * 100, 1) if total else None,
        "after_sell_avg_pct": round(mean(sell_returns) * 100, 2) if sell_returns else None,
        "after_sell_worst_avg_pct": round(mean(sell_worst) * 100, 2) if sell_worst else None,
        "all_days_avg_pct": round(mean(all_returns) * 100, 2) if all_returns else None,
        "note": f"과거 각 날짜에 같은 규칙을 적용해 {HORIZON}일 뒤 실제 방향과 비교했습니다. "
                "매수 신호는 상승, 매도 신호는 하락, 관망은 ±3% 이내일 때 적중으로 셉니다. "
                "baseline_up_pct 는 아무 신호 없이 '오른다'고만 했을 때의 적중률(매수 신호의 비교 기준), "
                "baseline_down_pct 는 '내린다'고만 했을 때의 적중률(매도 신호의 비교 기준)입니다. "
                "after_sell_avg_pct 는 매도 신호가 뜬 날 이후 7일 평균 변화율로, all_days_avg_pct(평소)보다 낮으면 "
                "그 신호에 팔았을 때 손실을 줄였다는 뜻입니다.",
    }


_cache: tuple[int, dict] | None = None  # (데이터 지문, 결과): 데이터가 같으면 백테스트를 다시 돌리지 않는다


def current_signal() -> dict:
    global _cache
    rows = data_service.list_data()
    if len(rows) < MIN_DAYS + HORIZON:
        return {"available": False, "message": f"신호 계산에는 최소 {MIN_DAYS + HORIZON}일 데이터가 필요합니다."}
    values = [r["value"] for r in rows]
    key = hash((rows[-1]["date"], tuple(values)))
    if _cache and _cache[0] == key:
        return dict(_cache[1])
    result = _compute(rows, values)
    _cache = (key, result)
    return dict(result)


def _compute(rows: list[dict], values: list[float]) -> dict:
    ind = indicators(values)
    score, reasons = _vote(ind)
    signal = _decide(score)

    # 7일 예상 범위: 최근 30일 일간 변동성으로 계산한 약 68% 범위 (방향 예측이 아니라 '흔들림 폭')
    spread = ind["daily_vol_pct"] / 100 * sqrt(HORIZON)
    price = ind["price"]
    bt = backtest(values)
    key = signal.lower()
    return {
        "available": True,
        "date": rows[-1]["date"],
        "price": round(price),
        "signal": signal,
        "label": LABELS[signal],
        "score": score,
        "level": level_for(score),
        "levels": [{"step": l["step"], "name": l["name"], "key": l["key"]} for l in LEVELS],
        "reasons": reasons,
        "indicators": {k: round(v, 2) for k, v in ind.items()},
        "forecast": {
            "horizon_days": HORIZON,
            "low": round(price * (1 - spread)),
            "high": round(price * (1 + spread)),
            "method": f"최근 30일 일간 변동성 {ind['daily_vol_pct']:.2f}% 기준, {HORIZON}일 뒤 가격이 약 68% 확률로 들어올 범위",
        },
        "backtest": bt,
        "this_signal_hit_rate_pct": bt[key]["hit_rate_pct"],
        "disclaimer": "규칙 기반 참고 신호이며 수익을 보장하지 않습니다. 투자 판단과 책임은 본인에게 있습니다.",
    }

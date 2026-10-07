"""보너스: GPT 가 필요할 때 호출하는 '도구(Function Calling)' 정의와 실행.

GPT 는 아래 TOOLS 의 description 을 읽고, 질문에 답하는 데 필요하다고 판단하면
도구 이름과 인자(JSON)를 돌려준다. 서버가 그 함수를 실제로 실행해 결과를 다시 GPT 에 넘긴다.
같은 기능은 MCP 서버(mcp_server/)에서도 HTTP API 를 통해 그대로 쓸 수 있다.
"""
import json
from datetime import date
from statistics import mean

from . import conversation_service, data_service

MAX_RANGE_ROWS = 120  # 토큰 절약: 한 번에 돌려줄 최대 일수

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_data_summary",
            "description": "저장된 비트코인 일별 종가 전체의 요약(기간, 개수, 평균, 최고·최저, 추세, 월별 통계)을 가져온다. "
                           "전체 흐름이나 대략적인 수치를 물을 때 쓴다.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": "추가 통계(상승일·하락일 수와 비율, 최대 낙폭 MDD 와 그 날짜, 월별 수익률)를 가져온다. "
                           "'몇 번 올랐어?', '가장 크게 떨어진 구간', '몇 월 수익률' 같은 질문에 쓴다.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_range",
            "description": "특정 기간의 일별 종가와 그 기간 통계(시작·끝 가격, 변화율, 평균, 최고·최저)를 가져온다. "
                           "'3월 가격', '지난주', '2025-01-01부터 2025-01-31까지'처럼 날짜가 정해진 질문에 쓴다. "
                           f"최대 {MAX_RANGE_ROWS}일까지 일별 값을 돌려준다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_conversations",
            "description": "저장된 이전 대화 목록(제목, 마지막 수정 시각, 메시지 수)을 가져온다. "
                           "'지난번에 뭐 물어봤지?' 같은 질문에 쓴다.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_LABELS = {
    "get_data_summary": "전체 요약 조회",
    "get_statistics": "추가 통계 조회",
    "get_price_range": "기간 데이터 조회",
    "list_conversations": "대화 목록 조회",
}


def price_range(start: date, end: date) -> dict:
    """기간 데이터와 통계. /api/data?start=&end= 와 도구가 함께 쓴다."""
    if start > end:
        start, end = end, start
    rows = [r for r in data_service.list_data() if start.isoformat() <= r["date"] <= end.isoformat()]
    if not rows:
        return {"start_date": start.isoformat(), "end_date": end.isoformat(), "count": 0, "message": "해당 기간 데이터가 없습니다."}
    values = [r["value"] for r in rows]
    hi = max(rows, key=lambda r: r["value"])
    lo = min(rows, key=lambda r: r["value"])
    return {
        "start_date": rows[0]["date"],
        "end_date": rows[-1]["date"],
        "count": len(rows),
        "first": round(values[0]),
        "last": round(values[-1]),
        "change_pct": round((values[-1] - values[0]) / values[0] * 100, 2),
        "average": round(mean(values)),
        "max": {"date": hi["date"], "value": round(hi["value"])},
        "min": {"date": lo["date"], "value": round(lo["value"])},
        "days": [{"date": r["date"], "value": round(r["value"]), **({"memo": r["memo"]} if r["memo"] else {})}
                 for r in rows[-MAX_RANGE_ROWS:]],
        "truncated": len(rows) > MAX_RANGE_ROWS,
    }


def run_tool(name: str, arguments: str) -> dict:
    """GPT 가 요청한 도구를 실행한다. 잘못된 인자는 오류 내용을 그대로 GPT 에 돌려준다."""
    try:
        args = json.loads(arguments or "{}")
        if name == "get_data_summary":
            return data_service.build_summary()
        if name == "get_statistics":
            st = data_service.build_statistics()
            return {k: v for k, v in st.items() if k != "series"}  # 그래프용 시계열은 너무 길어 제외
        if name == "get_price_range":
            return price_range(date.fromisoformat(args["start_date"]), date.fromisoformat(args["end_date"]))
        if name == "list_conversations":
            return {"conversations": conversation_service.list_conversations()[:20]}
        return {"error": f"알 수 없는 도구: {name}"}
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return {"error": f"인자가 올바르지 않습니다: {e}"}

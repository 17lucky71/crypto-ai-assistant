"""보너스: 비트코인 AI 비서 MCP 서버.

웹 화면의 GPT 가 쓰는 것과 같은 도구를 MCP(Model Context Protocol)로 연다.
Claude 데스크톱 같은 외부 AI 클라이언트가 이 서버를 통해 배포된 백엔드 API 를 호출한다.

  [Claude 데스크톱] --MCP(stdio)--> [이 server.py] --HTTP--> [Render 백엔드 API] --> [Firestore]

실행 확인: python server.py   (Claude 데스크톱 설정 방법은 README 참고)
환경 변수: API_BASE_URL (예: https://crypto-ai-assistant-j7ge.onrender.com)
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 70  # Render 무료 티어가 잠에서 깨는 시간(최대 1분)을 고려

mcp = FastMCP("bitcoin-ai-assistant")


def _get(path: str, params: dict | None = None):
    res = httpx.get(API_BASE_URL + path, params=params, timeout=TIMEOUT)
    res.raise_for_status()
    return res.json()


@mcp.tool()
def get_data_summary() -> dict:
    """저장된 비트코인 일별 종가(업비트 KRW-BTC) 전체 요약: 기간, 개수, 평균, 최고·최저(날짜 포함), 30일 변화율, 추세, 월별 통계."""
    return _get("/api/data/summary")


@mcp.tool()
def get_statistics() -> dict:
    """추가 통계: 상승일·하락일 수와 비율, 최대 낙폭(MDD)과 그 날짜, 월별 수익률."""
    data = _get("/api/data/statistics")
    data.pop("series", None)  # 그래프용 일별 시계열은 너무 길어 제외
    return data


@mcp.tool()
def get_price_range(start_date: str, end_date: str) -> dict:
    """특정 기간(YYYY-MM-DD ~ YYYY-MM-DD)의 일별 종가와 기간 통계(시작·끝 가격, 변화율, 평균, 최고·최저)."""
    return _get("/api/data/range", {"start": start_date, "end": end_date})


@mcp.tool()
def get_market_signals() -> dict:
    """오늘의 매매 신호(매수/매도/관망)와 근거, 7일 예상 가격 범위, 같은 규칙의 과거 적중률. 참고용이며 투자 판단은 본인 책임."""
    return _get("/api/signals")


@mcp.tool()
def get_recent_news(query: str = "비트코인", limit: int = 8) -> dict:
    """최근 7일 뉴스 헤드라인(제목, 언론사, 시각, 링크)."""
    return _get("/api/news", {"q": query, "limit": limit})


@mcp.tool()
def list_conversations() -> list:
    """웹 서비스에 저장된 이전 대화 목록(제목, 수정 시각, 메시지 수, id)."""
    return _get("/api/conversations")


@mcp.tool()
def get_conversation(conversation_id: str) -> dict:
    """특정 대화의 전체 메시지를 불러온다. id 는 list_conversations 결과에서 얻는다."""
    return _get(f"/api/conversations/{conversation_id}")


@mcp.tool()
def ask_assistant(question: str) -> dict:
    """웹 서비스의 GPT 비서에게 질문한다. 답변과 GPT 가 호출한 도구 목록을 돌려주고, 대화는 서비스에 저장된다."""
    res = httpx.post(API_BASE_URL + "/api/chat", json={"message": question}, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()
    return {"reply": data["reply"], "tool_calls": data.get("tool_calls", []), "conversation_id": data["conversation_id"]}


if __name__ == "__main__":
    mcp.run()  # 기본은 stdio: Claude 데스크톱이 이 프로세스를 직접 실행해 통신한다

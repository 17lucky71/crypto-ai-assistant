"""컨텍스트 주입 채팅.

흐름: 데이터 요약 조회 → 시스템 프롬프트에 삽입 → GPT 호출 → 대화 자동 저장
"""
import json

from openai import OpenAI

from ..config import settings
from . import conversation_service, data_service

SYSTEM_TEMPLATE = """당신은 사용자의 데이터를 이해하는 데이터 분석 비서입니다.
아래 [사용자 데이터 요약]만 근거로 한국어로 친절하고 간결하게 답하세요.

[사용자 데이터 요약]
- 데이터: {name} (단위: {unit})
- 데이터 기간: {period}
- 총 레코드: {count}개
- 주요 지표: {metrics}
- 최근 트렌드: {trend}
- 최근 14일 값: {recent}
- 월별 평균·최고·최저: {monthly}
- 메모가 있는 날: {notable}

답변 규칙:
1. 숫자는 요약에 있는 값만 쓰고, 금액은 "1억 6,500만 원"처럼 읽기 쉽게 표기합니다.
2. 요약에 없는 내용(예: 뉴스, 미래 가격)은 추측하지 말고 "데이터에 없다"고 말합니다.
3. 매수·매도 같은 투자 권유는 하지 않습니다. 필요하면 "투자 판단은 본인 책임"이라고 덧붙입니다.
4. 3~6문장 안으로 답합니다.
"""


class ChatUnavailable(Exception):
    """API 키가 없거나 OpenAI 호출이 실패했을 때."""


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build_system_prompt(summary: dict) -> str:
    return SYSTEM_TEMPLATE.format(
        name=summary["name"], unit=summary["unit"], period=summary["period"], count=summary["count"],
        metrics=_compact(summary["metrics"]), trend=summary["trend"], recent=_compact(summary["recent"]),
        monthly=_compact(summary["monthly"]), notable=_compact(summary["notable"]) if summary["notable"] else "없음",
    )


def _call_openai(messages: list[dict]) -> str:
    if not settings.OPENAI_API_KEY:
        raise ChatUnavailable("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=40)
        res = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=settings.OPENAI_MAX_TOKENS,
            temperature=0.4,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception as e:  # 네트워크, 키 오류, 한도 초과 등
        raise ChatUnavailable(f"AI 응답 생성에 실패했습니다: {e.__class__.__name__}") from e


def chat(message: str, conversation_id: str | None) -> dict:
    # 1) 데이터 요약 조회 (/api/data/summary 와 같은 함수)
    summary = data_service.build_summary()

    # 2) 이전 대화가 있으면 불러온다
    history: list[dict] = []
    if conversation_id:
        conv = conversation_service.get_conversation(conversation_id)
        if conv is None:
            raise LookupError("대화를 찾을 수 없습니다.")
        history = conv["messages"][-settings.CHAT_HISTORY_LIMIT:]

    # 3) 요약을 시스템 프롬프트에 넣어 GPT 호출
    messages = [{"role": "system", "content": build_system_prompt(summary)}, *history, {"role": "user", "content": message}]
    reply = _call_openai(messages)

    # 4) 대화 자동 저장
    new_msgs = [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
    if conversation_id:
        conversation_service.append_messages(conversation_id, new_msgs)
    else:
        conversation_id = conversation_service.create_conversation("", new_msgs)["id"]

    return {"reply": reply, "conversation_id": conversation_id, "summary_used": summary}

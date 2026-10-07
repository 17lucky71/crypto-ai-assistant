"""컨텍스트 주입 채팅.

흐름: 데이터 요약 조회 → 시스템 프롬프트에 삽입 → GPT 호출(필요하면 도구 호출) → 대화 자동 저장
"""
import json

from openai import OpenAI

from ..config import settings
from . import conversation_service, data_service, tools

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
1. 숫자는 요약이나 도구 결과에 있는 값만 쓰고, 금액은 "1억 6,500만 원"처럼 읽기 쉽게 표기합니다.
2. 요약에 없는 특정 기간·통계가 필요하면 제공된 도구를 호출해 확인한 뒤 답합니다. 없는 사실은 지어내지 않습니다.
3. "살까/팔까", "전망", "예측" 질문에는 get_market_signals 와 get_recent_news 를 호출한 뒤 다음 순서로 답합니다.
   ① 신호(매수 신호/매도 신호/관망)를 먼저 말합니다.
   ② 그 신호의 이유를 근거(reasons) 2~3개로 설명하고, 관련 있어 보이는 뉴스 제목이 있으면 함께 듭니다.
   ③ 반대 방향 근거가 있으면 한 줄로 덧붙입니다.
   ④ 7일 예상 범위와 이 신호의 과거 적중률(%)을 숫자로 알려 줍니다.
   ⑤ 마지막 줄에 "규칙 기반 참고 신호이며 투자 판단은 본인 책임입니다."를 붙입니다.
   "반드시 오른다/내린다"처럼 단정하지 않습니다.
4. 일반 질문은 3~6문장, 살까/팔까 질문은 8문장 안으로 답합니다.
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


MAX_TOOL_ROUNDS = 3  # 도구 호출을 주고받는 최대 횟수 (무한 반복·비용 방지)


def _client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise ChatUnavailable("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
    # OPENAI_BASE_URL 이 비어 있으면 OpenAI(GPT), 값이 있으면 그 주소의 OpenAI 호환 API 를 쓴다
    return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL or None, timeout=40)


def _complete(messages: list[dict], use_tools: bool):
    """OpenAI 호출 1회. 응답 message 객체를 돌려준다 (content 또는 tool_calls)."""
    client = _client()
    try:
        kwargs = dict(model=settings.OPENAI_MODEL, messages=messages,
                      max_tokens=settings.OPENAI_MAX_TOKENS, temperature=0.4)
        if use_tools:
            kwargs.update(tools=tools.TOOLS, tool_choice="auto")
        return client.chat.completions.create(**kwargs).choices[0].message
    except Exception as e:  # 네트워크, 키 오류, 한도 초과 등
        raise ChatUnavailable(f"AI 응답 생성에 실패했습니다: {e.__class__.__name__}") from e


def _run_with_tools(messages: list[dict]) -> tuple[str, list[dict]]:
    """Function Calling 루프: GPT 가 도구를 요청하면 실행해서 결과를 돌려주고, 최종 답변을 받는다."""
    used: list[dict] = []
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        msg = _complete(messages, use_tools=round_no < MAX_TOOL_ROUNDS)
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return (msg.content or "").strip(), used
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls],
        })
        for c in calls:
            result = tools.run_tool(c.function.name, c.function.arguments)
            used.append({"name": c.function.name, "label": tools.TOOL_LABELS.get(c.function.name, c.function.name),
                         "arguments": json.loads(c.function.arguments or "{}") if c.function.arguments else {}})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": _compact(result)})
    return "답변을 정리하지 못했어요. 질문을 조금 더 구체적으로 해 주세요.", used


def chat(message: str, conversation_id: str | None) -> dict:
    # 1) 데이터 요약 조회 (/api/data/summary 와 같은 함수)
    summary = data_service.build_summary()

    # 2) 이전 대화가 있으면 불러온다 (role, content 만 보낸다)
    history: list[dict] = []
    if conversation_id:
        conv = conversation_service.get_conversation(conversation_id)
        if conv is None:
            raise LookupError("대화를 찾을 수 없습니다.")
        history = [{"role": m["role"], "content": m["content"]} for m in conv["messages"][-settings.CHAT_HISTORY_LIMIT:]]

    # 3) 요약을 시스템 프롬프트에 넣어 GPT 호출 (필요하면 도구 호출)
    messages = [{"role": "system", "content": build_system_prompt(summary)}, *history, {"role": "user", "content": message}]
    reply, used = _run_with_tools(messages)

    # 4) 대화 자동 저장 (어떤 도구를 썼는지도 함께 기록)
    assistant_msg = {"role": "assistant", "content": reply}
    if used:
        assistant_msg["tools_used"] = [u["label"] for u in used]
    new_msgs = [{"role": "user", "content": message}, assistant_msg]
    if conversation_id:
        conversation_service.append_messages(conversation_id, new_msgs)
    else:
        conversation_id = conversation_service.create_conversation("", new_msgs)["id"]

    return {"reply": reply, "conversation_id": conversation_id, "summary_used": summary, "tool_calls": used}

"""컨텍스트 주입 채팅.

흐름: 데이터 요약 조회 → 시스템 프롬프트에 삽입 → GPT 호출(필요하면 도구 호출) → 대화 자동 저장
"""
import json

from openai import OpenAI

from ..config import settings
from . import conversation_service, data_service, signal_service, tools

SYSTEM_TEMPLATE = """당신은 '코인 위험 알리미'의 데이터 분석 비서입니다.
사용자의 비트코인 시세 데이터를 이해하고, 아래 [사용자 데이터 요약]을 근거로 한국어로 맞춤형 답변을 제공합니다.

[사용자 데이터 요약]
- 데이터: {name} (단위: {unit})
- 데이터 기간: {period}
- 총 레코드: {count}개
- 주요 지표: {metrics}
- 최근 트렌드: {trend}
- 오늘의 위험 단계: {risk}
- 최근 14일 값: {recent}
- 월별 평균·최고·최저: {monthly}
- 메모가 있는 날: {notable}

답변 규칙:
1. 결론(숫자)을 먼저 말하고, 비교 기준을 붙여 의미를 설명합니다. 예: "월평균 대비 8% 높은 수준이에요."
   금액은 "1억 1,344만 원"처럼 읽기 쉽게 쓰고, 숫자는 요약이나 도구 결과에 있는 값만 씁니다.
2. 요약만으로 답할 수 있으면 도구를 부르지 않습니다. 특정 날짜·기간, 추가 통계가 필요할 때만 도구를 호출합니다.
3. "팔까/살까", "위험해?", "전망", "예측" 질문에는 get_market_signals 와 get_recent_news 를 호출한 뒤
   ① 위험 단계와 신호 → ② 그 이유 2~3개(관련 뉴스 제목이 있으면 함께) → ③ 반대 근거 한 줄
   → ④ 7일 예상 범위와 과거 적중률 순서로 답하고, 마지막 줄에 "규칙 기반 참고 신호이며 투자 판단은 본인 책임입니다."를 붙입니다.
   "반드시 오른다/내린다"처럼 단정하지 않습니다.
4. 데이터나 도구 결과에 없는 내용은 지어내지 말고 "저장된 데이터에는 없어요"라고 말합니다.
5. 친근한 존댓말(~해요)로 2~5문장, 위험 질문은 8문장 안으로 답합니다.

답변 예시:
사용자: "이번 달 흐름이 어때?"
비서: "이번 달 평균은 1억 1,520만 원으로, 전체 월평균보다 4% 낮은 수준이에요. 월초보다는 1.9% 내려와 있고, 최근 30일 추세는 상승이에요."
사용자: "가장 비쌌던 때는?"
비서: "2025년 10월 8일에 1억 7,801만 원으로 가장 높았어요. 월평균으로는 2025-10이 가장 높은 달이었어요."
"""


class ChatUnavailable(Exception):
    """API 키가 없거나 OpenAI 호출이 실패했을 때."""


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _risk_line() -> str:
    """오늘의 위험 단계 한 줄 (계산 실패해도 채팅은 계속되게)."""
    try:
        sig = signal_service.current_signal()
    except Exception:
        return "계산 불가"
    if not sig.get("available"):
        return "계산 불가 (데이터 부족)"
    lv = sig["level"]
    top = [r["text"] for r in sig["reasons"] if r["score"] < 0][:3]
    return f"{lv['name']} ({sig['label']}, 점수 {sig['score']:+d})" + (f" — 하락 근거: {'; '.join(top)}" if top else "")


def build_system_prompt(summary: dict) -> str:
    return SYSTEM_TEMPLATE.format(
        name=summary["name"], unit=summary["unit"], period=summary["period"], count=summary["count"],
        metrics=_compact(summary["metrics"]), trend=summary["trend"], risk=_risk_line(), recent=_compact(summary["recent"]),
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

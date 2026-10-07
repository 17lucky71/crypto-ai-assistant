from fastapi import APIRouter, HTTPException, status

from ..schemas import ChatRequest, ChatResponse
from ..services import chat_service

router = APIRouter(prefix="/api/chat", tags=["AI 채팅"])


@router.post("", response_model=ChatResponse, summary="AI 대화 (데이터 요약 컨텍스트 주입 + 자동 저장)")
def chat(body: ChatRequest):
    try:
        return chat_service.chat(body.message, body.conversation_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except chat_service.ChatUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

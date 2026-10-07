from fastapi import APIRouter, HTTPException, status

from ..schemas import ConversationCreate, ConversationDetail, ConversationListItem
from ..services import conversation_service

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED, summary="대화 저장")
def create_conversation(body: ConversationCreate):
    return conversation_service.create_conversation(body.title, [m.model_dump(exclude_none=True) for m in body.messages])


@router.get("", response_model=list[ConversationListItem], summary="대화 목록 조회 (messages 미포함)")
def list_conversations():
    return conversation_service.list_conversations()


@router.get("/{conv_id}", response_model=ConversationDetail, summary="특정 대화 불러오기 (messages 포함)")
def get_conversation(conv_id: str):
    conv = conversation_service.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    return conv


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT, summary="대화 삭제")
def delete_conversation(conv_id: str):
    if conversation_service.get_conversation(conv_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    conversation_service.delete_conversation(conv_id)

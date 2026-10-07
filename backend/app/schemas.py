"""요청·응답 데이터 형식. Pydantic 이 잘못된 입력을 422 오류로 막아 준다."""
from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------- 데이터 ----------
class DataCreate(BaseModel):
    date: Date = Field(..., description="날짜 (YYYY-MM-DD)", examples=["2025-10-01"])
    value: float = Field(..., gt=0, lt=1e12, description="일별 종가(원), 0보다 커야 함", examples=[165000000])
    memo: str = Field("", max_length=200, description="메모 (최대 200자)", examples=["ETF 승인 기대감"])

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, v: str) -> str:
        return v.strip()


class DataUpdate(BaseModel):
    """수정은 바꿀 항목만 보내면 된다."""
    date: Date | None = None
    value: float | None = Field(None, gt=0, lt=1e12)
    memo: str | None = Field(None, max_length=200)


class DataItem(BaseModel):
    id: str
    date: Date
    value: float
    memo: str = ""


class DataSummary(BaseModel):
    name: str
    unit: str
    period: str
    count: int
    metrics: dict
    trend: str
    recent: list[dict] = Field(default_factory=list, description="최근 14일 값")
    monthly: list[dict] = Field(default_factory=list, description="월별 평균·최고·최저")
    notable: list[dict] = Field(default_factory=list, description="메모가 있는 날 (최근 20개)")


class DataStatistics(BaseModel):
    count: int
    up_days: int = Field(description="전날보다 오른 날 수")
    down_days: int = Field(description="전날보다 내린 날 수")
    up_ratio_pct: float | None = Field(description="상승일 비율(%)")
    max_drawdown: dict | None = Field(description="최대 낙폭: 고점 대비 가장 크게 떨어진 비율과 날짜")
    monthly_returns: list[dict] = Field(description="월별 수익률(월초 대비 월말)")
    series: list[dict] = Field(description="그래프용: 날짜, 종가, 7일·30일 이동평균")


# ---------- 대화 ----------
class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ConversationCreate(BaseModel):
    title: str = Field("", max_length=100)
    messages: list[Message] = Field(default_factory=list, max_length=200)


class ConversationListItem(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationDetail(ConversationListItem):
    messages: list[Message]


# ---------- 채팅 ----------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, examples=["최근 한 달 비트코인 흐름이 어때?"])
    conversation_id: str | None = Field(None, description="이어서 대화할 때 대화 id")

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("메시지가 비어 있습니다.")
        return v.strip()


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    summary_used: DataSummary

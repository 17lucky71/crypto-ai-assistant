"""FastAPI 진입점. 실행: uvicorn main:app --reload"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import STORE_KIND
from app.routers import chat, conversations, data, signals

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="비트코인 AI 비서 API",
    description="업비트 KRW-BTC 일별 종가를 저장·요약하고, 그 요약을 GPT 시스템 프롬프트에 넣어 답하는 API",
    version="1.0.0",
)

# CORS: 프론트엔드(Vercel) 주소만 허용한다. "*" 하나만 넣으면 전체 허용.
origins = settings.ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Alert-Token"],
)

app.include_router(data.router)
app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(signals.router)


@app.get("/", tags=["상태"], summary="서버 상태 확인 (프론트의 콜드스타트 확인용)")
def health():
    return {"status": "ok", "storage": STORE_KIND, "docs": "/docs"}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    # 예상 못 한 오류도 프론트가 읽을 수 있는 JSON 으로 돌려준다
    logging.exception("처리되지 않은 오류")
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})

import hmac

from fastapi import APIRouter, Header, HTTPException, Query, status

from ..config import settings
from ..services import alert_service, market_service, news_service, signal_service

router = APIRouter(tags=["매매 신호·뉴스·알림"])


@router.get("/api/signals", summary="(보너스) 오늘의 위험 단계·매매 신호 + 근거 + 7일 예상 범위 + 과거 적중률")
def get_signal():
    return signal_service.current_signal()


@router.get("/api/news", summary="(보너스) 최근 7일 뉴스 헤드라인 (구글 뉴스 RSS)")
def get_news(q: str | None = Query(None, max_length=50, description="검색어, 비우면 '비트코인'"),
             limit: int = Query(8, ge=1, le=20)):
    return news_service.recent_news(q, limit)


def _check_token(token: str | None) -> None:
    if not settings.ALERT_TOKEN:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ALERT_TOKEN 환경 변수가 설정되지 않았습니다.")
    if not token or not hmac.compare_digest(token, settings.ALERT_TOKEN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "알림 토큰이 올바르지 않습니다.")


@router.post("/api/alerts/run", summary="(보너스) 시세 갱신 → 위험 단계 계산 → 디스코드 알림. 스케줄러가 매일 호출 (force=true 는 X-Alert-Token 필요)")
def run_alert(x_alert_token: str | None = Header(None), force: bool = Query(False, description="단계가 그대로여도 보내기 (토큰 필요)")):
    # 일반 실행은 '단계가 바뀔 때만' 보내므로 여러 번 불려도 중복 알림이 없다 → 토큰 없이 허용.
    # 강제 전송(force)만 토큰으로 보호한다.
    if force:
        _check_token(x_alert_token)
    try:
        return alert_service.run(force=force)
    except alert_service.AlertConfigError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except OSError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"디스코드 전송 실패: {e.__class__.__name__}")


@router.get("/api/alerts/history", summary="(보너스) 디스코드로 보낸 위험 알림 기록 (최신순)")
def alert_history(limit: int = Query(10, ge=1, le=50)):
    return alert_service.history(limit)


@router.post("/api/market/update", summary="(보너스) 업비트에서 빠진 날짜 시세만 추가 (X-Alert-Token 필요)")
def update_market(x_alert_token: str | None = Header(None)):
    _check_token(x_alert_token)
    return market_service.update_latest()

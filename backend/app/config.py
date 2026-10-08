"""환경 변수 설정을 한곳에서 읽는다. 키 값은 코드에 절대 적지 않는다."""
import os

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    # OpenAI (기본). OPENAI_BASE_URL 을 바꾸면 OpenAI 호환 API(예: Gemini)로도 동작한다.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "500"))

    # Firebase: JSON 문자열(배포용) 또는 키 파일 경로(로컬용) 중 하나
    FIREBASE_SERVICE_ACCOUNT_JSON: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    FIREBASE_SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "")

    # CORS 허용 도메인 (쉼표로 구분). 비워 두면 로컬 개발 주소만 허용
    ALLOWED_ORIGINS: list[str] = _split(
        os.getenv("ALLOWED_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000")
    )

    # 데이터 이름 (요약·프롬프트에 표시)
    DATA_NAME: str = os.getenv("DATA_NAME", "비트코인 일별 종가 (업비트 KRW-BTC)")
    DATA_UNIT: str = os.getenv("DATA_UNIT", "원")

    # 매매 신호 알림 (보너스): 디스코드 웹훅 주소와, 알림 실행 API 를 보호하는 비밀 토큰
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    ALERT_TOKEN: str = os.getenv("ALERT_TOKEN", "")
    # risk(기본): 위험 단계가 '주의' 이상으로 올라가거나 위험이 풀릴 때만 / change: 단계가 바뀔 때마다 / daily: 매일
    ALERT_MODE: str = os.getenv("ALERT_MODE", "risk")
    # 디스코드 메시지에서 눌러 들어갈 대시보드 주소
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://crypto-ai-assistant-frontend-lake.vercel.app")
    NEWS_QUERY: str = os.getenv("NEWS_QUERY", "비트코인")

    # 채팅에 함께 보낼 이전 대화 개수 (토큰 절약)
    CHAT_HISTORY_LIMIT: int = int(os.getenv("CHAT_HISTORY_LIMIT", "10"))


settings = Settings()

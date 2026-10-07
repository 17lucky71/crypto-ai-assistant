"""최근 뉴스 헤드라인 (구글 뉴스 RSS, API 키 불필요).

AI 가 '왜 오르/내리는지'를 설명할 때 근거로 쓰고, 디스코드 알림에도 붙인다.
30분 동안은 같은 결과를 재사용해 외부 요청을 줄인다.
"""
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from ..config import settings

CACHE_SECONDS = 30 * 60
_cache: dict[str, tuple[float, dict]] = {}


def _fetch(query: str, limit: int) -> dict:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{query} when:7d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (crypto-ai-assistant)"})
    with urllib.request.urlopen(req, timeout=8) as res:
        root = ET.fromstring(res.read())
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]  # 제목 끝의 " - 언론사" 제거
        try:
            published = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone().strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            published = ""
        items.append({"title": title, "source": source, "published": published, "link": (it.findtext("link") or "").strip()})
    items.sort(key=lambda x: x["published"], reverse=True)
    return {"query": query, "count": min(limit, len(items)), "items": items[:limit]}


def recent_news(query: str | None = None, limit: int = 8) -> dict:
    query = (query or settings.NEWS_QUERY).strip()[:50]
    key = f"{query}|{limit}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        data = _fetch(query, limit)
    except Exception as e:  # 네트워크 오류 등: 서비스 전체가 멈추지 않게 오류 내용만 돌려준다
        return {"query": query, "count": 0, "items": [], "error": f"뉴스를 가져오지 못했습니다: {e.__class__.__name__}"}
    _cache[key] = (time.time(), data)
    return data

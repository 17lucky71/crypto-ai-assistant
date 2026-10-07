"""대화 기록 저장·조회."""
from datetime import datetime, timezone

from ..db import CONVERSATION_COLLECTION, store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_title(messages: list[dict]) -> str:
    first = next((m["content"] for m in messages if m["role"] == "user"), "새 대화")
    first = " ".join(first.split())
    return first if len(first) <= 30 else first[:30] + "…"


def _list_item(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "title": doc.get("title") or "새 대화",
        "message_count": len(doc.get("messages", [])),
        "created_at": doc.get("created_at", ""),
        "updated_at": doc.get("updated_at", ""),
    }


def list_conversations() -> list[dict]:
    """최근 수정 순. 목록에는 messages 를 넣지 않는다 (불러오기는 GET /{id})."""
    docs = store.list(CONVERSATION_COLLECTION)
    return sorted((_list_item(d) for d in docs), key=lambda x: x["updated_at"], reverse=True)


def get_conversation(conv_id: str) -> dict | None:
    doc = store.get(CONVERSATION_COLLECTION, conv_id)
    if doc is None:
        return None
    return {**_list_item(doc), "messages": doc.get("messages", [])}


def create_conversation(title: str, messages: list[dict]) -> dict:
    now = _now()
    doc = {"title": title or _make_title(messages), "messages": messages, "created_at": now, "updated_at": now}
    conv_id = store.add(CONVERSATION_COLLECTION, doc)
    return get_conversation(conv_id)


def append_messages(conv_id: str, new_messages: list[dict]) -> dict:
    doc = store.get(CONVERSATION_COLLECTION, conv_id)
    messages = doc.get("messages", []) + new_messages
    store.update(CONVERSATION_COLLECTION, conv_id, {"messages": messages, "updated_at": _now()})
    return get_conversation(conv_id)


def delete_conversation(conv_id: str) -> None:
    store.delete(CONVERSATION_COLLECTION, conv_id)

"""Firestore 연결.

- 배포: FIREBASE_SERVICE_ACCOUNT_JSON 환경 변수에 서비스 계정 JSON 전체를 넣는다.
- 로컬: FIREBASE_SERVICE_ACCOUNT_PATH 에 키 파일 경로를 넣는다 (파일은 .gitignore 처리).
- 둘 다 없으면 메모리 저장소로 동작한다 (서버를 끄면 사라지는 개발용 임시 저장소).
"""
import json
import logging
import uuid
from copy import deepcopy

from .config import settings

logger = logging.getLogger(__name__)

DATA_COLLECTION = "data"
CONVERSATION_COLLECTION = "conversations"


class MemoryStore:
    """Firestore 키가 없을 때 쓰는 아주 단순한 대체 저장소 (개발·테스트용)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {DATA_COLLECTION: {}, CONVERSATION_COLLECTION: {}}

    def list(self, collection: str) -> list[dict]:
        return [{"id": k, **deepcopy(v)} for k, v in self._data[collection].items()]

    def get(self, collection: str, doc_id: str) -> dict | None:
        doc = self._data[collection].get(doc_id)
        return {"id": doc_id, **deepcopy(doc)} if doc is not None else None

    def add(self, collection: str, data: dict, doc_id: str | None = None) -> str:
        doc_id = doc_id or uuid.uuid4().hex[:20]
        self._data[collection][doc_id] = deepcopy(data)
        return doc_id

    def update(self, collection: str, doc_id: str, data: dict) -> None:
        self._data[collection][doc_id].update(deepcopy(data))

    def delete(self, collection: str, doc_id: str) -> None:
        self._data[collection].pop(doc_id, None)


class FirestoreStore:
    """MemoryStore 와 같은 메서드를 Firestore 로 구현한다."""

    def __init__(self, client) -> None:
        self.client = client

    def list(self, collection: str) -> list[dict]:
        return [{"id": d.id, **d.to_dict()} for d in self.client.collection(collection).stream()]

    def get(self, collection: str, doc_id: str) -> dict | None:
        snap = self.client.collection(collection).document(doc_id).get()
        return {"id": snap.id, **snap.to_dict()} if snap.exists else None

    def add(self, collection: str, data: dict, doc_id: str | None = None) -> str:
        ref = self.client.collection(collection).document(doc_id) if doc_id else self.client.collection(collection).document()
        ref.set(data)
        return ref.id

    def update(self, collection: str, doc_id: str, data: dict) -> None:
        self.client.collection(collection).document(doc_id).update(data)

    def delete(self, collection: str, doc_id: str) -> None:
        self.client.collection(collection).document(doc_id).delete()


def _create_store():
    cred_info = None
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        cred_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
    elif settings.FIREBASE_SERVICE_ACCOUNT_PATH:
        with open(settings.FIREBASE_SERVICE_ACCOUNT_PATH, encoding="utf-8") as f:
            cred_info = json.load(f)

    if cred_info is None:
        logger.warning("Firebase 키가 없어 메모리 저장소로 실행합니다. 서버를 끄면 데이터가 사라집니다.")
        return MemoryStore(), "memory"

    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_info))
    return FirestoreStore(firestore.client()), "firestore"


store, STORE_KIND = _create_store()

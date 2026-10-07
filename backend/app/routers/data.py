from fastapi import APIRouter, HTTPException, Query, status

from ..schemas import DataCreate, DataItem, DataSummary, DataUpdate
from ..services import data_service

router = APIRouter(prefix="/api/data", tags=["데이터"])


@router.get("/summary", response_model=DataSummary, summary="데이터 요약 (프롬프트 주입용)")
def get_summary():
    return data_service.build_summary()


@router.get("", response_model=list[DataItem], summary="데이터 목록 조회")
def list_data(
    order: str = Query("desc", pattern="^(asc|desc)$", description="날짜 정렬 (asc/desc)"),
    limit: int | None = Query(None, ge=1, le=5000, description="최대 개수"),
):
    rows = data_service.list_data()
    if order == "desc":
        rows = rows[::-1]
    return rows[:limit] if limit else rows


@router.post("", response_model=DataItem, status_code=status.HTTP_201_CREATED, summary="새 데이터 추가")
def create_data(body: DataCreate):
    if data_service.find_by_date(body.date):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.date} 날짜의 데이터가 이미 있습니다. 수정(PUT)을 사용하세요.")
    return data_service.create_data(body.date, body.value, body.memo)


@router.put("/{doc_id}", response_model=DataItem, summary="데이터 수정")
def update_data(doc_id: str, body: DataUpdate):
    if data_service.get_data(doc_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "해당 데이터를 찾을 수 없습니다.")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "수정할 항목이 없습니다.")
    if "memo" in changes:
        changes["memo"] = changes["memo"].strip()
    if "date" in changes:
        other = data_service.find_by_date(changes["date"])
        if other and other["id"] != doc_id:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{changes['date']} 날짜의 데이터가 이미 있습니다.")
    return data_service.update_data(doc_id, changes)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, summary="데이터 삭제")
def delete_data(doc_id: str):
    if data_service.get_data(doc_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "해당 데이터를 찾을 수 없습니다.")
    data_service.delete_data(doc_id)

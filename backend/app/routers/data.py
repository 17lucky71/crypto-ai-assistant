import csv
import io
import json
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from ..schemas import DataCreate, DataItem, DataStatistics, DataSummary, DataUpdate
from ..services import data_service

router = APIRouter(prefix="/api/data", tags=["데이터"])


@router.get("/summary", response_model=DataSummary, summary="데이터 요약 (프롬프트 주입용)")
def get_summary():
    return data_service.build_summary()


@router.get("/statistics", response_model=DataStatistics, summary="추가 통계 (보너스: 이동평균, 상승일 비율, 최대 낙폭, 월별 수익률)")
def get_statistics():
    return data_service.build_statistics()


@router.get("/export", summary="데이터 내보내기 (보너스: CSV 또는 JSON 파일 다운로드)")
def export_data(format: str = Query("csv", pattern="^(csv|json)$", description="csv 또는 json")):
    rows = data_service.list_data()
    stamp = date.today().strftime("%Y%m%d")
    if format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2)
        return Response(body, media_type="application/json; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="btc_daily_{stamp}.json"'})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["date", "value", "memo"], extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    # 엑셀에서 한글이 깨지지 않도록 BOM 을 붙인다
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="btc_daily_{stamp}.csv"'})


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

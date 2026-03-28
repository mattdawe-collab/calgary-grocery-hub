from fastapi import APIRouter, Query, HTTPException
from api.data import store

router = APIRouter()


@router.get("/deals")
def list_deals(
    category: str | None = None,
    store_name: str | None = Query(None, alias="store"),
    search: str | None = None,
    preset: str | None = None,
    min_score: int | None = None,
    sort: str = "score_desc",
    offset: int = 0,
    limit: int = Query(50, le=200),
):
    deals, total = store.get_deals(
        category=category,
        store=store_name,
        search=search,
        preset=preset,
        min_score=min_score,
        sort=sort,
        offset=offset,
        limit=limit,
    )
    return {"deals": deals, "total": total, "offset": offset, "limit": limit}


@router.get("/deals/{deal_id}")
def get_deal(deal_id: int):
    deal = store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return deal


@router.get("/deals/{deal_id}/history")
def get_deal_history(deal_id: int):
    result = store.get_deal_history(deal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return result

from fastapi import APIRouter
from api.data import store

router = APIRouter()


@router.get("/insights")
def get_insights():
    return store.insights


@router.post("/reload")
def reload_data():
    store.load()
    return {"status": "ok", "deals": len(store.current), "historical": len(store.historical)}

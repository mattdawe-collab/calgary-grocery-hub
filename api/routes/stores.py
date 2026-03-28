from fastapi import APIRouter
from api.data import store

router = APIRouter()


@router.get("/stores")
def list_stores():
    return store.get_stores()


@router.get("/categories")
def list_categories():
    return store.get_categories()

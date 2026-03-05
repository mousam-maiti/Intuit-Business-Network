"""Search routes: GET /search."""
from fastapi import APIRouter, Depends, Query

from dependencies import get_search_service
from services.search_service import SearchService

router = APIRouter()


@router.get("/search")
def search_entities(
    q: str = Query(None),
    industry: str = Query(None),
    sortBy: str = Query(None),
    svc: SearchService = Depends(get_search_service),
):
    return svc.search(q=q, industry=industry, sort_by=sortBy)

"""Search routes: GET /search."""
from fastapi import APIRouter, Request, Query

router = APIRouter()


@router.get("/search")
def search_entities(
    request: Request,
    q: str = Query(None),
    industry: str = Query(None),
    sortBy: str = Query(None),
):
    mysql = request.app.state.mysql
    results = mysql.search_entities(q=q, industry=industry, sort_by=sortBy)
    return {"data": results, "total": len(results)}

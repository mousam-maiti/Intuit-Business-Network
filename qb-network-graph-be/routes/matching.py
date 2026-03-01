"""Matching routes: GET /matching/pending, POST /matching/{id}/resolve, POST /matching/resolve."""
from fastapi import APIRouter, Request, HTTPException

from models.api import ResolveRequest, AdHocResolveRequest

router = APIRouter()


@router.get("/matching/pending")
def get_pending_matches(request: Request):
    mysql = request.app.state.mysql
    matches = mysql.get_pending_matches()
    return {"data": matches}


@router.post("/matching/{match_id}/resolve")
def resolve_match(request: Request, match_id: str, body: ResolveRequest):
    mysql = request.app.state.mysql
    try:
        result = mysql.resolve_match(match_id, body.resolution)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resolution failed: {e}")
    return {"data": result}


@router.post("/matching/resolve")
def resolve_adhoc(request: Request, body: AdHocResolveRequest):
    neo4j = request.app.state.neo4j
    result = neo4j.resolve_adhoc(
        name=body.name, ein=body.ein,
        city=body.city, state=body.state,
        industry=body.industry,
    )
    return {"data": result}

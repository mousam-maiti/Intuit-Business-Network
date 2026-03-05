"""Matching routes: GET /matching/pending, GET /matching/{id}/candidates, POST /matching/{id}/resolve, POST /matching/resolve."""
from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_matching_service, get_search_service
from models.api import ResolveRequest, AdHocResolveRequest
from services.matching_service import MatchingService
from services.search_service import SearchService

router = APIRouter()


@router.get("/matching/pending")
def get_pending_matches(svc: MatchingService = Depends(get_matching_service)):
    return svc.get_pending()


@router.get("/matching/{match_id}/candidates")
def get_candidates(
    match_id: str,
    svc: MatchingService = Depends(get_matching_service),
):
    try:
        return svc.get_candidates(match_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Candidate lookup failed: {e}")


@router.post("/matching/{match_id}/resolve")
def resolve_match(
    match_id: str,
    body: ResolveRequest,
    svc: MatchingService = Depends(get_matching_service),
):
    try:
        return svc.resolve(match_id, body.resolution, candidate_override_id=body.candidateGoldenId)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resolution failed: {e}")


@router.post("/matching/resolve")
def resolve_adhoc(
    body: AdHocResolveRequest,
    svc: SearchService = Depends(get_search_service),
):
    return svc.resolve_adhoc(
        name=body.name, ein=body.ein,
        city=body.city, state=body.state,
        industry=body.industry,
    )

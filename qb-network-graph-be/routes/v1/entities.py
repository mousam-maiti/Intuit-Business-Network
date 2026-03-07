"""Entity routes: GET/PATCH /entities, GET /entities/{id}."""
from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_entity_service
from exceptions import EntityNotFoundError
from services.entity_service import EntityService

router = APIRouter()


@router.get("/entities")
def list_entities(
    q: str = Query(None),
    industry: str = Query(None),
    company_id: str = Query(None),
    svc: EntityService = Depends(get_entity_service),
):
    return svc.list_entities(q=q, industry=industry, company_id=company_id)


@router.get("/entities/{entity_id}")
def get_entity(
    entity_id: str,
    svc: EntityService = Depends(get_entity_service),
):
    try:
        return svc.get_entity(entity_id)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.patch("/entities/{entity_id}")
def patch_entity(
    entity_id: str,
    body: dict,
    svc: EntityService = Depends(get_entity_service),
):
    try:
        return svc.patch_entity(entity_id, body)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found")

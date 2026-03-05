"""Lineage routes: entities, trail, snapshot, restore."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from dependencies import get_lineage_service
from services.lineage_service import LineageService

router = APIRouter(prefix="/lineage")


class RestoreRequest(BaseModel):
    audit_id: str
    snapshot: dict


@router.get("/entities")
def lineage_entities(svc: LineageService = Depends(get_lineage_service)):
    return svc.get_entities()


@router.get("/trail/{entity_id}")
def audit_trail(
    entity_id: str,
    limit: int = Query(100),
    svc: LineageService = Depends(get_lineage_service),
):
    return svc.get_trail(entity_id, limit)


@router.get("/snapshot/{entity_id}")
def entity_snapshot(
    entity_id: str,
    date: str = Query(...),
    svc: LineageService = Depends(get_lineage_service),
):
    return svc.get_snapshot(entity_id, date)


@router.post("/restore/{entity_id}")
def restore_entity(
    entity_id: str,
    body: RestoreRequest,
    svc: LineageService = Depends(get_lineage_service),
):
    return svc.restore(entity_id, body.snapshot, body.audit_id)

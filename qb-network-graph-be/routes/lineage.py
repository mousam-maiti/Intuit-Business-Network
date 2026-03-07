"""Lineage routes: entities, trail, snapshot, restore."""
from fastapi import APIRouter, Request, Query
from pydantic import BaseModel

router = APIRouter(prefix="/lineage")


class RestoreRequest(BaseModel):
    audit_id: str
    snapshot: dict


@router.get("/entities")
def lineage_entities(request: Request):
    neo4j = request.app.state.neo4j
    return {"data": neo4j.get_lineage_entities()}


@router.get("/trail/{entity_id}")
def audit_trail(request: Request, entity_id: str, limit: int = Query(100)):
    neo4j = request.app.state.neo4j
    return {"data": neo4j.get_audit_trail(entity_id, limit)}


@router.get("/snapshot/{entity_id}")
def entity_snapshot(request: Request, entity_id: str, date: str = Query(...)):
    neo4j = request.app.state.neo4j
    return {"data": neo4j.get_entity_snapshot(entity_id, date)}


@router.post("/restore/{entity_id}")
def restore_entity(request: Request, entity_id: str, body: RestoreRequest):
    neo4j = request.app.state.neo4j
    result = neo4j.restore_entity(entity_id, body.snapshot, body.audit_id)
    return {"data": result}

"""
Sync HTTP endpoints — push Paimon gold data to Neo4j serving layer.

Called by the Classifier Orchestrator after writing to Paimon gold.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/golden-record")
async def sync_golden_record(request: Request):
    """Upsert a golden record to Neo4j + invalidate Redis."""
    body = await request.json()
    sync_service = request.app.state.sync_service
    result = await sync_service.sync_golden_record(body)
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.post("/relationship")
async def sync_relationship(request: Request):
    """Create a relationship edge in Neo4j."""
    body = await request.json()
    sync_service = request.app.state.sync_service
    result = await sync_service.sync_relationship(body)
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.post("/audit")
async def sync_audit(request: Request):
    """Create an audit entry node in Neo4j."""
    body = await request.json()
    sync_service = request.app.state.sync_service
    result = await sync_service.sync_audit(body)
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.post("/backfill-embeddings")
async def backfill_embeddings(request: Request):
    """Backfill embedding vectors for all entities that lack them."""
    sync_service = request.app.state.sync_service
    result = await sync_service.backfill_embeddings()
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.get("/candidates/{entity_id}")
async def get_candidates_for_entity(entity_id: str, request: Request):
    """Find candidate golden records for an entity using vector search."""
    candidate_service = request.app.state.candidate_service
    result = candidate_service.find_candidates_for_entity(entity_id)
    return JSONResponse(content=result, status_code=200)


@router.post("/pending-resolution")
async def sync_pending_resolution(request: Request):
    """Acknowledge a pending resolution."""
    body = await request.json()
    sync_service = request.app.state.sync_service
    result = await sync_service.sync_pending_resolution(body)
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.post("/transfer-relationships")
async def transfer_relationships(request: Request):
    """Transfer all relationships from an absorbed entity to the survivor after a merge."""
    body = await request.json()
    sync_service = request.app.state.sync_service
    result = await sync_service.transfer_relationships(
        absorbed_id=body["absorbed_id"],
        survivor_id=body["survivor_id"],
    )
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)


@router.post("/backfill-relationship-volumes")
async def backfill_relationship_volumes(request: Request):
    """Backfill relationship edge volumes from entity behavioral data.

    Fixes edges with volume=0 when the connected entity has
    avg_transaction and transaction_count (race condition during startup).
    """
    sync_service = request.app.state.sync_service
    result = await sync_service.backfill_relationship_volumes()
    status = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status)

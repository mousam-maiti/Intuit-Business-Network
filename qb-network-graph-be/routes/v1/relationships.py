"""Relationship routes: GET /relationships, /entities/{id}/relationships|network|volume."""
from fastapi import APIRouter, Depends, Query

from dependencies import get_relationship_service
from services.relationship_service import RelationshipService

router = APIRouter()


@router.get("/relationships")
def get_all_relationships(
    company_id: str = Query(None),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_all(company_id=company_id)


@router.get("/entities/{entity_id}/relationships")
def get_entity_relationships(
    entity_id: str,
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_for_entity(entity_id)


@router.get("/entities/{entity_id}/network")
def get_network(
    entity_id: str,
    depth: int = Query(2),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_network(entity_id, depth=depth)


@router.get("/entities/{entity_id}/supply-chain")
def get_supply_chain(
    entity_id: str,
    direction: str = Query("upstream"),
    depth: int = Query(5),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_supply_chain(entity_id, direction=direction, depth=depth)


@router.get("/entities/{id_a}/shortest-path/{id_b}")
def get_shortest_path(
    id_a: str,
    id_b: str,
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_shortest_path(id_a, id_b)


@router.get("/entities/{id_a}/common-neighbors/{id_b}")
def get_common_neighbors(
    id_a: str,
    id_b: str,
    limit: int = Query(20),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_common_neighbors(id_a, id_b, limit=limit)


@router.get("/entities/{entity_id}/cluster")
def get_cluster(
    entity_id: str,
    max_size: int = Query(20),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_cluster(entity_id, max_size=max_size)


@router.get("/entities/{entity_id}/impact")
def get_impact(
    entity_id: str,
    max_depth: int = Query(3),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_impact(entity_id, max_depth=max_depth)


@router.get("/entities/{entity_id}/volume")
def get_volume(
    entity_id: str,
    company_id: str = Query(None),
    svc: RelationshipService = Depends(get_relationship_service),
):
    return svc.get_volume(entity_id, company_id=company_id)

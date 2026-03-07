"""Relationship routes: GET /relationships, /entities/{id}/relationships|network|volume."""
from fastapi import APIRouter, Request, Query

router = APIRouter()


@router.get("/relationships")
def get_all_relationships(request: Request, company_id: str = Query(None)):
    neo4j = request.app.state.neo4j
    rels = neo4j.get_all_relationships(company_id=company_id)
    return {"data": rels}


@router.get("/entities/{entity_id}/relationships")
def get_entity_relationships(request: Request, entity_id: str):
    neo4j = request.app.state.neo4j
    rels = neo4j.get_entity_relationships(entity_id)
    return {"data": rels}


@router.get("/entities/{entity_id}/network")
def get_network(request: Request, entity_id: str, depth: int = Query(2)):
    neo4j = request.app.state.neo4j
    graph = neo4j.get_network(entity_id, depth=depth)
    return {"data": graph}


@router.get("/entities/{entity_id}/supply-chain")
def get_supply_chain(request: Request, entity_id: str,
                     direction: str = Query("upstream"), depth: int = Query(5)):
    neo4j = request.app.state.neo4j
    result = neo4j.get_supply_chain(entity_id, direction=direction, max_depth=depth)
    return {"data": result}


@router.get("/entities/{id_a}/shortest-path/{id_b}")
def get_shortest_path(request: Request, id_a: str, id_b: str):
    neo4j = request.app.state.neo4j
    result = neo4j.get_shortest_path(id_a, id_b)
    return {"data": result}


@router.get("/entities/{id_a}/common-neighbors/{id_b}")
def get_common_neighbors(request: Request, id_a: str, id_b: str,
                         limit: int = Query(20)):
    neo4j = request.app.state.neo4j
    result = neo4j.get_common_neighbors(id_a, id_b, limit=limit)
    return {"data": result}


@router.get("/entities/{entity_id}/cluster")
def get_cluster(request: Request, entity_id: str,
                max_size: int = Query(20)):
    neo4j = request.app.state.neo4j
    result = neo4j.get_cluster(entity_id, max_size=max_size)
    return {"data": result}


@router.get("/entities/{entity_id}/impact")
def get_impact(request: Request, entity_id: str,
               max_depth: int = Query(3)):
    neo4j = request.app.state.neo4j
    result = neo4j.get_impact(entity_id, max_depth=max_depth)
    return {"data": result}


@router.get("/entities/{entity_id}/volume")
def get_volume(request: Request, entity_id: str, company_id: str = Query(None)):
    # Volume reads from MySQL bills table (source data)
    mysql = request.app.state.mysql
    volume = mysql.get_monthly_volume(entity_id, company_id=company_id)
    return {"data": volume}

"""Relationship routes: GET /relationships, /entities/{id}/relationships|network|volume."""
from fastapi import APIRouter, Request, Query

router = APIRouter()


@router.get("/relationships")
def get_all_relationships(request: Request, company_id: str = Query(None)):
    mysql = request.app.state.mysql
    rels = mysql.get_all_relationships(company_id=company_id)
    return {"data": rels}


@router.get("/entities/{entity_id}/relationships")
def get_entity_relationships(request: Request, entity_id: str):
    mysql = request.app.state.mysql
    rels = mysql.get_entity_relationships(entity_id)
    return {"data": rels}


@router.get("/entities/{entity_id}/network")
def get_network(request: Request, entity_id: str, depth: int = Query(2)):
    mysql = request.app.state.mysql
    graph = mysql.get_network(entity_id, depth=depth)
    return {"data": graph}


@router.get("/entities/{entity_id}/volume")
def get_volume(request: Request, entity_id: str, company_id: str = Query(None)):
    mysql = request.app.state.mysql
    volume = mysql.get_monthly_volume(entity_id, company_id=company_id)
    return {"data": volume}

"""FastAPI Depends() providers — extract services from app.state."""
from fastapi import Request

from services.entity_service import EntityService
from services.relationship_service import RelationshipService
from services.search_service import SearchService
from services.matching_service import MatchingService
from services.connection_service import ConnectionService
from services.native_service import NativeService
from services.alert_service import AlertService
from services.lineage_service import LineageService


def get_entity_service(request: Request) -> EntityService:
    return request.app.state.entity_service


def get_relationship_service(request: Request) -> RelationshipService:
    return request.app.state.relationship_service


def get_search_service(request: Request) -> SearchService:
    return request.app.state.search_service


def get_matching_service(request: Request) -> MatchingService:
    return request.app.state.matching_service


def get_connection_service(request: Request) -> ConnectionService:
    return request.app.state.connection_service


def get_native_service(request: Request) -> NativeService:
    return request.app.state.native_service


def get_alert_service(request: Request) -> AlertService:
    return request.app.state.alert_service


def get_lineage_service(request: Request) -> LineageService:
    return request.app.state.lineage_service

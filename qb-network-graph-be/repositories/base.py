"""Abstract base classes for all repositories."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class AbstractEntityRepository(ABC):
    @abstractmethod
    def get_all(self, q: str = None, industry: str = None, company_id: str = None) -> list[dict]:
        ...

    @abstractmethod
    def get_by_id(self, entity_id: str) -> Optional[dict]:
        ...

    @abstractmethod
    def update(self, entity_id: str, fields: dict) -> Optional[dict]:
        ...


class AbstractRelationshipRepository(ABC):
    @abstractmethod
    def get_all(self, company_id: str = None) -> list[dict]:
        ...

    @abstractmethod
    def get_for_entity(self, entity_id: str) -> list[dict]:
        ...

    @abstractmethod
    def get_network(self, entity_id: str, depth: int = 2) -> dict:
        ...

    @abstractmethod
    def get_supply_chain(self, entity_id: str, direction: str = "upstream", max_depth: int = 3) -> dict:
        ...

    @abstractmethod
    def get_shortest_path(self, id_a: str, id_b: str) -> dict:
        ...

    @abstractmethod
    def get_common_neighbors(self, id_a: str, id_b: str, limit: int = 20) -> dict:
        ...

    @abstractmethod
    def get_cluster(self, entity_id: str, max_size: int = 20) -> dict:
        ...

    @abstractmethod
    def get_impact(self, entity_id: str, max_depth: int = 3) -> dict:
        ...


class AbstractSearchRepository(ABC):
    @abstractmethod
    def search(self, q: str = None, industry: str = None, sort_by: str = None, limit: int = 100) -> list[dict]:
        ...

    @abstractmethod
    def resolve_adhoc(self, name: str = None, ein: str = None,
                      city: str = None, state: str = None,
                      industry: str = None) -> dict:
        ...


class AbstractLineageRepository(ABC):
    @abstractmethod
    def get_entities_with_audit(self) -> list[dict]:
        ...

    @abstractmethod
    def get_audit_trail(self, entity_id: str, limit: int = 100) -> list[dict]:
        ...

    @abstractmethod
    def get_snapshot(self, entity_id: str, date: str) -> Optional[dict]:
        ...

    @abstractmethod
    def restore(self, entity_id: str, snapshot: dict, audit_id: str) -> dict:
        ...


class AbstractResolutionRepository(ABC):
    @abstractmethod
    def get_pending(self, neo4j_client=None, relationship_client=None) -> list[dict]:
        ...

    @abstractmethod
    def resolve(self, match_id: str, resolution: str, candidate_override_id: str = None) -> dict:
        ...

    def get_orphan_golden_id(self, match_id: str) -> Optional[str]:
        """Return the orphan_golden_id for a given match_id."""
        return None


class AbstractConnectionRepository(ABC):
    @abstractmethod
    def get_auto(self, user_id: str = "1") -> list[dict]:
        ...

    @abstractmethod
    def get_manual(self, user_id: str = "1") -> list[dict]:
        ...

    @abstractmethod
    def add(self, payload: dict, user_id: str = "1") -> dict:
        ...

    @abstractmethod
    def update_agent_status(self, connection_id: str, status: str,
                            decision: str = None, golden_record_id: str = None):
        ...


class AbstractNativeRepository(ABC):
    @abstractmethod
    def get_all_overrides(self, user_id: str = "1") -> dict:
        ...

    @abstractmethod
    def get_override(self, entity_id: str, user_id: str = "1") -> Optional[dict]:
        ...

    @abstractmethod
    def save_override(self, entity_id: str, fields: dict, user_id: str = "1") -> dict:
        ...

    @abstractmethod
    def delete_override_field(self, entity_id: str, field: str, user_id: str = "1") -> Optional[dict]:
        ...

    @abstractmethod
    def get_merges(self, user_id: str = "1") -> list[dict]:
        ...

    @abstractmethod
    def create_merge(self, payload: dict, user_id: str = "1") -> dict:
        ...

    @abstractmethod
    def delete_merge(self, merge_id: str, user_id: str = "1") -> Optional[dict]:
        ...


class AbstractAlertRepository(ABC):
    @abstractmethod
    def insert(self, alert_id: str, connection_id: str, alert_type: str,
               title: str, message: str = None, entity_name: str = None,
               target_entity_id: str = None, confidence: float = None,
               user_id: str = "1"):
        ...

    @abstractmethod
    def get_all(self, user_id: str = "1") -> list[dict]:
        ...

    @abstractmethod
    def dismiss(self, alert_id: str):
        ...


class AbstractVolumeRepository(ABC):
    @abstractmethod
    def get_monthly_volume(self, entity_id: str, company_id: str = None) -> list[dict]:
        ...

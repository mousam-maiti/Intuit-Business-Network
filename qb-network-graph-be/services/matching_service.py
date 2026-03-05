"""Matching service — pending matches, candidate lookup, and resolution."""
from __future__ import annotations

import logging

import httpx

from repositories.base import AbstractResolutionRepository

logger = logging.getLogger(__name__)


class MatchingService:
    def __init__(self, resolution_repo: AbstractResolutionRepository, entity_repo=None, relationship_repo=None, sync_url: str = "http://localhost:8084"):
        self._repo = resolution_repo
        self._entity_repo = entity_repo
        self._relationship_repo = relationship_repo
        self._sync_url = sync_url

    def get_pending(self) -> dict:
        return {"data": self._repo.get_pending(neo4j_client=self._entity_repo, relationship_client=self._relationship_repo)}

    def get_candidates(self, match_id: str) -> dict:
        """Fetch candidate golden records for a pending match's orphan entity."""
        orphan_golden_id = self._repo.get_orphan_golden_id(match_id)
        if not orphan_golden_id:
            return {"candidates": [], "error": f"Match {match_id} not found"}
        try:
            resp = httpx.get(f"{self._sync_url}/sync/candidates/{orphan_golden_id}", timeout=10.0)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch candidates for {orphan_golden_id}: {e}")
            return {"candidates": [], "error": str(e)}

    def resolve(self, match_id: str, resolution: str, candidate_override_id: str = None) -> dict:
        result = self._repo.resolve(match_id, resolution, candidate_override_id=candidate_override_id)
        return {"data": result}

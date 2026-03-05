"""Search service — full-text search and ad-hoc resolution."""
from __future__ import annotations

from repositories.base import AbstractSearchRepository


class SearchService:
    def __init__(self, search_repo: AbstractSearchRepository):
        self._repo = search_repo

    def search(self, q: str = None, industry: str = None,
               sort_by: str = None) -> dict:
        results = self._repo.search(q=q, industry=industry, sort_by=sort_by)
        return {"data": results, "total": len(results)}

    def resolve_adhoc(self, name: str = None, ein: str = None,
                      city: str = None, state: str = None,
                      industry: str = None) -> dict:
        return {"data": self._repo.resolve_adhoc(
            name=name, ein=ein, city=city, state=state, industry=industry,
        )}

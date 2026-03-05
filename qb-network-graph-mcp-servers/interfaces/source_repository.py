"""Abstract interface for source data reads (MySQL OLTP only)."""
from abc import ABC, abstractmethod
from typing import Optional


class AbstractSourceRepository(ABC):
    """Source data reads from MySQL OLTP tables (companies, vendors, etc.)."""

    @abstractmethod
    def get_company(self, company_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_all_companies(self) -> list[dict]: ...

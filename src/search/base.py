"""Abstract base class for search providers."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from ..parser import Endpoint


class SearchResult(BaseModel):
    """A search result containing an endpoint and its similarity score."""

    endpoint: Endpoint
    similarity_score: float  # 0.0 to 1.0
    low_confidence: bool = False


class SearchProvider(ABC):
    """Abstract interface for search providers."""

    @abstractmethod
    def search(
        self,
        query: str,
        endpoints: list[Endpoint],
        limit: int = 5,
    ) -> list[SearchResult]:
        """
        Search for endpoints matching the query.

        Args:
            query: Natural language search query
            endpoints: List of endpoints to search
            limit: Maximum number of results to return

        Returns:
            List of SearchResult sorted by similarity score descending
        """
        pass

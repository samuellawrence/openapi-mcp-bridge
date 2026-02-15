"""Search providers for endpoint discovery."""

from .base import SearchProvider, SearchResult
from .fuzzy import FuzzySearchProvider

# Lazy import for embedding provider (requires extra dependencies)
def get_embedding_provider(**kwargs):
    """Get an EmbeddingSearchProvider instance (requires sentence-transformers)."""
    from .embedding import EmbeddingSearchProvider
    return EmbeddingSearchProvider(**kwargs)

__all__ = ["SearchProvider", "SearchResult", "FuzzySearchProvider", "get_embedding_provider"]

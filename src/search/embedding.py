"""Embedding-based semantic search provider using sentence-transformers."""

import logging
from typing import Any

import numpy as np

from ..parser import Endpoint
from .base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

# Lazy import sentence-transformers to avoid loading it if not used
_model = None


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Lazy load the sentence transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {model_name}")
            _model = SentenceTransformer(model_name)
            logger.info("Embedding model loaded successfully")
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for embedding search. "
                "Install with: pip install sentence-transformers"
            )
    return _model


class EmbeddingSearchProvider(SearchProvider):
    """
    Embedding-based semantic search provider.

    Uses sentence-transformers to generate embeddings for endpoints
    and compute cosine similarity for search queries.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        confidence_threshold: float = 0.4,
    ):
        """
        Initialize the embedding search provider.

        Args:
            model_name: Name of the sentence-transformers model to use.
            confidence_threshold: Results below this score are flagged as low_confidence.
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self._embeddings_cache: dict[str, np.ndarray] = {}
        self._endpoint_texts: dict[str, str] = {}

    def _get_endpoint_key(self, endpoint: Endpoint) -> str:
        """Generate a unique key for an endpoint."""
        return f"{endpoint.method}:{endpoint.path}"

    def _build_searchable_text(self, endpoint: Endpoint) -> str:
        """
        Build a searchable text string from endpoint metadata.

        Combines summary, description, operationId, tags, and path words.
        """
        parts = []

        if endpoint.summary:
            parts.append(endpoint.summary)

        if endpoint.description:
            parts.append(endpoint.description)

        if endpoint.operation_id:
            # Convert camelCase to words: getPetById -> get Pet By Id
            op_id = endpoint.operation_id
            words = []
            current_word = []
            for char in op_id:
                if char.isupper() and current_word:
                    words.append("".join(current_word))
                    current_word = [char.lower()]
                else:
                    current_word.append(char)
            if current_word:
                words.append("".join(current_word))
            parts.append(" ".join(words))

        if endpoint.tags:
            parts.extend(endpoint.tags)

        # Convert path to words: /pet/{petId} -> pet petId
        path_words = endpoint.path.replace("/", " ").replace("{", "").replace("}", "")
        parts.append(path_words)

        # Add HTTP method
        parts.append(endpoint.method.lower())

        return " ".join(parts)

    def _ensure_embeddings(self, endpoints: list[Endpoint]) -> None:
        """
        Generate embeddings for endpoints that don't have cached embeddings.

        Args:
            endpoints: List of endpoints to generate embeddings for.
        """
        model = _get_model(self.model_name)

        # Find endpoints that need embeddings
        texts_to_embed = []
        keys_to_embed = []

        for endpoint in endpoints:
            key = self._get_endpoint_key(endpoint)
            if key not in self._embeddings_cache:
                text = self._build_searchable_text(endpoint)
                self._endpoint_texts[key] = text
                texts_to_embed.append(text)
                keys_to_embed.append(key)

        if texts_to_embed:
            logger.info(f"Generating embeddings for {len(texts_to_embed)} endpoints")
            embeddings = model.encode(texts_to_embed, convert_to_numpy=True)

            for key, embedding in zip(keys_to_embed, embeddings):
                self._embeddings_cache[key] = embedding

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity between 0 and 1.
        """
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        similarity = dot_product / (norm_a * norm_b)
        # Normalize to 0-1 range (cosine similarity is -1 to 1)
        return (similarity + 1) / 2

    def search(
        self,
        query: str,
        endpoints: list[Endpoint],
        limit: int = 5,
    ) -> list[SearchResult]:
        """
        Search for endpoints using semantic similarity.

        Args:
            query: Natural language search query.
            endpoints: List of endpoints to search through.
            limit: Maximum number of results to return.

        Returns:
            List of SearchResult sorted by similarity score descending.
        """
        if not endpoints:
            return []

        # Ensure all endpoints have embeddings
        self._ensure_embeddings(endpoints)

        # Embed the query
        model = _get_model(self.model_name)
        query_embedding = model.encode(query, convert_to_numpy=True)

        # Compute similarities
        results = []
        for endpoint in endpoints:
            key = self._get_endpoint_key(endpoint)
            endpoint_embedding = self._embeddings_cache.get(key)

            if endpoint_embedding is not None:
                score = self._cosine_similarity(query_embedding, endpoint_embedding)
                results.append(
                    SearchResult(
                        endpoint=endpoint,
                        similarity_score=score,
                        low_confidence=score < self.confidence_threshold,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        return results[:limit]

    def clear_cache(self) -> None:
        """Clear the embeddings cache."""
        self._embeddings_cache.clear()
        self._endpoint_texts.clear()

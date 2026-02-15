"""Fuzzy search implementation using thefuzz library."""

from thefuzz import fuzz

from ..parser import Endpoint
from .base import SearchProvider, SearchResult


class FuzzySearchProvider(SearchProvider):
    """Fuzzy string matching search provider using thefuzz library."""

    def __init__(self, confidence_threshold: float = 0.4):
        """
        Initialize the fuzzy search provider.

        Args:
            confidence_threshold: Results below this score are flagged as low_confidence.
        """
        self.confidence_threshold = confidence_threshold

    def search(
        self,
        query: str,
        endpoints: list[Endpoint],
        limit: int = 5,
    ) -> list[SearchResult]:
        """
        Search for endpoints using fuzzy string matching.

        Args:
            query: Natural language search query.
            endpoints: List of endpoints to search through.
            limit: Maximum number of results to return.

        Returns:
            List of SearchResult sorted by similarity score descending.
        """
        results = []

        for endpoint in endpoints:
            searchable_text = self._build_searchable_text(endpoint)
            score = self._calculate_similarity(query, searchable_text)

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

    def _calculate_similarity(self, query: str, text: str) -> float:
        """
        Calculate similarity score between query and text.

        Uses token_set_ratio from thefuzz for better partial matching.

        Args:
            query: The search query.
            text: The text to compare against.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        # token_set_ratio handles word order and partial matches well
        score = fuzz.token_set_ratio(query.lower(), text.lower())
        return score / 100.0  # Convert from 0-100 to 0.0-1.0

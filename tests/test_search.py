"""Tests for search providers."""

from pathlib import Path

import pytest

from src.parser import OpenAPIParser
from src.search.fuzzy import FuzzySearchProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PETSTORE_SPEC = FIXTURES_DIR / "petstore.json"


class TestFuzzySearchProvider:
    """Tests for fuzzy search."""

    @pytest.fixture
    async def endpoints(self):
        """Load endpoints from petstore spec."""
        if not PETSTORE_SPEC.exists():
            pytest.skip("Petstore spec not found")
        parser = OpenAPIParser()
        spec = await parser.parse(str(PETSTORE_SPEC))
        return spec.endpoints

    @pytest.fixture
    def search_provider(self):
        return FuzzySearchProvider(confidence_threshold=0.4)

    @pytest.mark.asyncio
    async def test_find_all_pets(self, search_provider, endpoints):
        """Test searching for 'find all pets'."""
        results = search_provider.search("find all pets", endpoints, limit=5)

        assert len(results) > 0
        # findPetsByStatus should be a top result
        top_paths = [r.endpoint.path for r in results[:3]]
        assert any("findByStatus" in p or "/pet" in p for p in top_paths)

    @pytest.mark.asyncio
    async def test_create_pet(self, search_provider, endpoints):
        """Test searching for 'create a new pet'."""
        results = search_provider.search("create a new pet", endpoints, limit=5)

        assert len(results) > 0
        # POST /pet should be high
        top_result = results[0]
        assert top_result.similarity_score > 0.4
        # Should find pet-related endpoint
        assert "pet" in top_result.endpoint.path.lower()

    @pytest.mark.asyncio
    async def test_delete_pet(self, search_provider, endpoints):
        """Test searching for 'delete a pet'."""
        results = search_provider.search("delete a pet", endpoints, limit=5)

        assert len(results) > 0
        # DELETE method endpoints should rank high
        delete_in_top_3 = any(
            r.endpoint.method == "DELETE" for r in results[:3]
        )
        assert delete_in_top_3

    @pytest.mark.asyncio
    async def test_store_inventory(self, search_provider, endpoints):
        """Test searching for 'store inventory'."""
        results = search_provider.search("store inventory", endpoints, limit=5)

        assert len(results) > 0
        # /store/inventory should be top
        top_paths = [r.endpoint.path for r in results[:3]]
        assert any("inventory" in p.lower() for p in top_paths)

    @pytest.mark.asyncio
    async def test_nonsense_query_low_confidence(self, search_provider, endpoints):
        """Test that nonsense queries return low confidence results."""
        results = search_provider.search("xyzabc123qwerty", endpoints, limit=5)

        assert len(results) > 0
        # All results should be low confidence
        assert all(r.low_confidence for r in results)

    @pytest.mark.asyncio
    async def test_results_sorted_by_score(self, search_provider, endpoints):
        """Test that results are sorted by score descending."""
        results = search_provider.search("pet", endpoints, limit=10)

        assert len(results) > 1
        scores = [r.similarity_score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_limit_parameter(self, search_provider, endpoints):
        """Test that limit parameter works correctly."""
        results_5 = search_provider.search("pet", endpoints, limit=5)
        results_3 = search_provider.search("pet", endpoints, limit=3)
        results_1 = search_provider.search("pet", endpoints, limit=1)

        assert len(results_5) == 5
        assert len(results_3) == 3
        assert len(results_1) == 1

    @pytest.mark.asyncio
    async def test_search_by_method(self, search_provider, endpoints):
        """Test searching by HTTP method."""
        results = search_provider.search("POST pet", endpoints, limit=5)

        assert len(results) > 0
        # POST endpoints should rank high
        top_3_methods = [r.endpoint.method for r in results[:3]]
        assert "POST" in top_3_methods

    @pytest.mark.asyncio
    async def test_confidence_threshold(self, endpoints):
        """Test that confidence threshold affects low_confidence flag."""
        # High threshold - most results should be low confidence
        high_threshold = FuzzySearchProvider(confidence_threshold=0.9)
        results = high_threshold.search("get pets", endpoints, limit=5)
        low_conf_count = sum(1 for r in results if r.low_confidence)
        assert low_conf_count >= 3  # Most should be flagged

        # Low threshold - fewer results should be low confidence
        low_threshold = FuzzySearchProvider(confidence_threshold=0.2)
        results = low_threshold.search("get pets", endpoints, limit=5)
        low_conf_count = sum(1 for r in results if r.low_confidence)
        assert low_conf_count <= 2  # Few should be flagged

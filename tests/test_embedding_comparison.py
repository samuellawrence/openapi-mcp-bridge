"""Comparison tests between fuzzy and embedding search providers."""

from pathlib import Path

import pytest

from src.parser import OpenAPIParser
from src.search.fuzzy import FuzzySearchProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PETSTORE_SPEC = FIXTURES_DIR / "petstore.json"

# Test queries for comparison
COMPARISON_QUERIES = [
    ("find all pets", "Basic query"),
    ("what animals are available", "Synonym test"),
    ("buy a pet", "Semantic similarity test"),
    ("how many pets are in stock", "Intent matching test"),
    ("remove a specific animal", "Synonym + intent test"),
]


def format_results(results, limit=3):
    """Format search results for display."""
    output = []
    for i, r in enumerate(results[:limit]):
        output.append(
            f"  {i+1}. {r.endpoint.method} {r.endpoint.path} "
            f"(score: {r.similarity_score:.3f}, low_conf: {r.low_confidence})"
        )
    return "\n".join(output)


@pytest.fixture
async def endpoints():
    """Load endpoints from petstore spec."""
    if not PETSTORE_SPEC.exists():
        pytest.skip("Petstore spec not found")
    parser = OpenAPIParser()
    spec = await parser.parse(str(PETSTORE_SPEC))
    return spec.endpoints


@pytest.fixture
def fuzzy_provider():
    """Create fuzzy search provider."""
    return FuzzySearchProvider(confidence_threshold=0.4)


class TestFuzzySearchBaseline:
    """Test fuzzy search as baseline for comparison."""

    @pytest.mark.asyncio
    async def test_find_all_pets(self, fuzzy_provider, endpoints):
        """Test 'find all pets' query."""
        results = fuzzy_provider.search("find all pets", endpoints, limit=5)
        assert len(results) > 0
        # Should find pet-related endpoints
        assert any("pet" in r.endpoint.path.lower() for r in results[:3])

    @pytest.mark.asyncio
    async def test_synonym_query(self, fuzzy_provider, endpoints):
        """Test synonym query 'what animals are available'."""
        results = fuzzy_provider.search("what animals are available", endpoints, limit=5)
        assert len(results) > 0
        # Fuzzy search might struggle with synonyms

    @pytest.mark.asyncio
    async def test_semantic_query(self, fuzzy_provider, endpoints):
        """Test semantic query 'buy a pet'."""
        results = fuzzy_provider.search("buy a pet", endpoints, limit=5)
        assert len(results) > 0
        # Should ideally find store/order endpoints

    @pytest.mark.asyncio
    async def test_intent_query(self, fuzzy_provider, endpoints):
        """Test intent query 'how many pets are in stock'."""
        results = fuzzy_provider.search("how many pets are in stock", endpoints, limit=5)
        assert len(results) > 0
        # Should find inventory endpoint

    @pytest.mark.asyncio
    async def test_complex_query(self, fuzzy_provider, endpoints):
        """Test complex query 'remove a specific animal'."""
        results = fuzzy_provider.search("remove a specific animal", endpoints, limit=5)
        assert len(results) > 0
        # Should find DELETE endpoints


class TestEmbeddingSearch:
    """Test embedding search (requires sentence-transformers)."""

    @pytest.fixture
    def embedding_provider(self):
        """Create embedding search provider."""
        from src.search.embedding import EmbeddingSearchProvider
        return EmbeddingSearchProvider(confidence_threshold=0.4)

    @pytest.mark.asyncio
    async def test_find_all_pets(self, embedding_provider, endpoints):
        """Test 'find all pets' query with embeddings."""
        results = embedding_provider.search("find all pets", endpoints, limit=5)
        assert len(results) > 0
        assert any("pet" in r.endpoint.path.lower() for r in results[:3])

    @pytest.mark.asyncio
    async def test_synonym_query(self, embedding_provider, endpoints):
        """Test synonym query with embeddings - should perform better."""
        results = embedding_provider.search("what animals are available", endpoints, limit=5)
        assert len(results) > 0
        # Embedding search should understand "animals" = "pets"
        top_paths = [r.endpoint.path for r in results[:3]]
        assert any("pet" in p.lower() for p in top_paths)

    @pytest.mark.asyncio
    async def test_semantic_query(self, embedding_provider, endpoints):
        """Test semantic query with embeddings."""
        results = embedding_provider.search("buy a pet", endpoints, limit=5)
        assert len(results) > 0
        # Should find store/order endpoints
        top_paths = [r.endpoint.path for r in results[:3]]
        assert any("store" in p.lower() or "order" in p.lower() for p in top_paths)


def print_comparison_table(fuzzy_results, embedding_results, query):
    """Print a comparison table for manual inspection."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")
    print("\nFuzzy Search Results:")
    print(format_results(fuzzy_results))
    print("\nEmbedding Search Results:")
    print(format_results(embedding_results))
    print()


class TestSearchComparison:
    """Run comparison between fuzzy and embedding search."""

    @pytest.mark.asyncio
    async def test_run_comparison(self, endpoints):
        """Run full comparison and print results."""
        from src.search.embedding import EmbeddingSearchProvider

        fuzzy = FuzzySearchProvider(confidence_threshold=0.4)
        embedding = EmbeddingSearchProvider(confidence_threshold=0.4)

        print("\n" + "="*70)
        print("SEARCH PROVIDER COMPARISON: Fuzzy vs Embedding")
        print("="*70)

        for query, description in COMPARISON_QUERIES:
            fuzzy_results = fuzzy.search(query, endpoints, limit=3)
            embedding_results = embedding.search(query, endpoints, limit=3)
            print_comparison_table(fuzzy_results, embedding_results, f"{query} ({description})")

        # This test always passes - it's for manual inspection
        assert True

"""Tests for Context Assembler service (Phase 2.5B)."""

from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from app.services.context_assembler import (
    AssembledContext,
    AssembledMemoryItem,
    ContextAssembler,
    ContextAssemblyConfig,
)
from app.services.retrieval_policy import ScoredMemory


def _make_candidate(
    mem_id: str,
    content: str,
    category: str = "preference",
    source: str = "manual",
    importance: float = 0.8,
    confidence: float = 0.9,
    retrieval_score: float = 0.85,
    hybrid_score: float = 0.75,
    recency_score: float = 0.95,
) -> ScoredMemory:
    """Helper to create a realistic ScoredMemory candidate."""
    mock_memory = MagicMock()
    mock_memory.id = mem_id
    mock_memory.content = content
    mock_memory.category = category
    mock_memory.memory_type = category
    mock_memory.source = source
    mock_memory.importance = importance
    mock_memory.confidence = confidence

    return ScoredMemory(
        memory=mock_memory,
        similarity=0.8,
        keyword_score=0.7,
        hybrid_score=hybrid_score,
        recency_score=recency_score,
        retrieval_score=retrieval_score,
    )


def test_normal_assembly():
    """Verify standard assembly of multiple candidates into an AssembledContext."""
    c1 = _make_candidate("id-1", "User prefers dark mode.", retrieval_score=0.90)
    c2 = _make_candidate("id-2", "User writes Python.", retrieval_score=0.80)

    assembler = ContextAssembler()
    context = assembler.assemble([c1, c2])

    assert isinstance(context, AssembledContext)
    assert context.total_memories == 2
    assert len(context.items) == 2
    assert context.total_chars == len("User prefers dark mode.") + len("User writes Python.")

    # Check first item details
    item1 = context.items[0]
    assert isinstance(item1, AssembledMemoryItem)
    assert item1.id == "id-1"
    assert item1.content == "User prefers dark mode."
    assert item1.retrieval_score == 0.90
    assert item1.is_truncated is False
    assert item1.original_char_count == len("User prefers dark mode.")

    # Formatting & serialization
    text = context.format_text()
    assert "[1] (preference) User prefers dark mode." in text
    assert "[2] (preference) User writes Python." in text

    d = context.to_dict()
    assert d["total_memories"] == 2
    assert len(d["items"]) == 2


def test_empty_candidates():
    """Verify empty input returns a valid empty AssembledContext without errors."""
    assembler = ContextAssembler()
    context = assembler.assemble([])

    assert isinstance(context, AssembledContext)
    assert context.total_memories == 0
    assert context.total_chars == 0
    assert context.items == []
    assert context.format_text() == ""
    assert context.to_dict()["total_memories"] == 0


def test_max_memories_truncation():
    """Verify that context truncates after reaching max_memories limit."""
    config = ContextAssemblyConfig(max_memories=2)
    assembler = ContextAssembler(config=config)

    candidates = [
        _make_candidate(f"id-{i}", f"Content item {i}", retrieval_score=1.0 - i * 0.1)
        for i in range(5)
    ]

    context = assembler.assemble(candidates)

    assert context.total_memories == 2
    assert len(context.items) == 2
    assert context.items[0].id == "id-0"
    assert context.items[1].id == "id-1"


def test_single_content_truncation():
    """Verify single memory content exceeding max_content_chars is safely truncated."""
    config = ContextAssemblyConfig(max_content_chars=20)
    assembler = ContextAssembler(config=config)

    long_text = "This is a very long memory content that definitely exceeds twenty characters."
    short_text = "Short text."

    c1 = _make_candidate("id-1", long_text)
    c2 = _make_candidate("id-2", short_text)

    context = assembler.assemble([c1, c2])

    assert context.total_memories == 2

    # c1 should be truncated
    item1 = context.items[0]
    assert len(item1.content) == 20
    assert item1.content == long_text[:20]
    assert item1.is_truncated is True
    assert item1.original_char_count == len(long_text)

    # c2 should not be truncated
    item2 = context.items[1]
    assert len(item2.content) == len(short_text)
    assert item2.content == short_text
    assert item2.is_truncated is False
    assert item2.original_char_count == len(short_text)


def test_does_not_mutate_original_memory():
    """Verify truncation does not mutate the original Memory object's content."""
    config = ContextAssemblyConfig(max_content_chars=15)
    assembler = ContextAssembler(config=config)

    original_text = "Original pristine content that should not be touched."
    cand = _make_candidate("id-1", original_text)

    context = assembler.assemble([cand])

    # Context has truncated content
    assert context.items[0].content == original_text[:15]
    assert context.items[0].is_truncated is True

    # Original memory object content is strictly untouched
    assert cand.memory.content == original_text


def test_total_context_budget_truncation():
    """Verify that adding memories does not exceed max_context_chars total budget."""
    # Budget: 350 chars total. Candidates are 150 chars each.
    # Item 1 (150) -> fits (150 <= 350)
    # Item 2 (150) -> fits (300 <= 350)
    # Item 3 (150) -> 300 + 150 = 450 > 350 -> exceeds budget, omitted!
    config = ContextAssemblyConfig(max_context_chars=350, max_content_chars=500)
    assembler = ContextAssembler(config=config)

    c1 = _make_candidate("id-1", "A" * 150, retrieval_score=0.9)
    c2 = _make_candidate("id-2", "B" * 150, retrieval_score=0.8)
    c3 = _make_candidate("id-3", "C" * 150, retrieval_score=0.7)

    context = assembler.assemble([c1, c2, c3])

    assert context.total_memories == 2
    assert context.total_chars == 300
    assert context.total_chars <= config.max_context_chars
    assert [item.id for item in context.items] == ["id-1", "id-2"]


def test_deduplication_by_memory_id():
    """Verify deduplication removes duplicate IDs while preserving identical contents with distinct IDs."""
    assembler = ContextAssembler()

    c1 = _make_candidate("id-dup", "Shared knowledge content", retrieval_score=0.95)
    c2 = _make_candidate("id-other", "Shared knowledge content", retrieval_score=0.85)
    c3 = _make_candidate("id-dup", "Updated knowledge content", retrieval_score=0.75)

    context = assembler.assemble([c1, c2, c3])

    # c1 and c2 should be preserved (different IDs even though content is identical)
    # c3 should be skipped because id-dup was already encountered
    assert context.total_memories == 2
    assert [item.id for item in context.items] == ["id-dup", "id-other"]
    assert context.items[0].retrieval_score == 0.95  # First encounter kept


def test_field_integrity_and_scores_preserved():
    """Verify all fields and scores are faithfully preserved without scaling or tampering."""
    cand = _make_candidate(
        mem_id="mem-999",
        content="Important fact",
        category="identity",
        source="ai_extracted",
        importance=0.88,
        confidence=0.92,
        retrieval_score=0.8421,
        hybrid_score=0.7812,
        recency_score=0.9654,
    )

    assembler = ContextAssembler()
    context = assembler.assemble([cand])

    item = context.items[0]
    assert item.id == "mem-999"
    assert item.memory_type == "identity"
    assert item.content == "Important fact"
    assert item.source == "ai_extracted"
    assert item.importance == 0.88
    assert item.confidence == 0.92
    assert item.retrieval_score == 0.8421
    assert item.hybrid_score == 0.7812
    assert item.recency_score == 0.9654
    assert item.is_truncated is False
    assert item.original_char_count == len("Important fact")


def test_stable_ordering():
    """Verify assembled context strictly preserves the input retrieval policy order."""
    assembler = ContextAssembler()

    c_first = _make_candidate("id-10", "First item", retrieval_score=0.99)
    c_second = _make_candidate("id-05", "Second item", retrieval_score=0.88)
    c_third = _make_candidate("id-01", "Third item", retrieval_score=0.77)

    context = assembler.assemble([c_first, c_second, c_third])

    assert [item.id for item in context.items] == ["id-10", "id-05", "id-01"]


def test_boundary_values():
    """Verify boundary conditions: single character limits and exact matches."""
    config = ContextAssemblyConfig(
        max_memories=1,
        max_content_chars=5,
        max_context_chars=5,
    )
    assembler = ContextAssembler(config=config)

    # Exact match of 5 chars
    cand = _make_candidate("id-1", "12345")
    context = assembler.assemble([cand])

    assert context.total_memories == 1
    assert context.total_chars == 5
    assert context.items[0].content == "12345"
    assert context.items[0].is_truncated is False

    # 1 char config boundary
    config_1 = ContextAssemblyConfig(max_memories=1, max_content_chars=1, max_context_chars=1)
    assembler_1 = ContextAssembler(config=config_1)
    context_1 = assembler_1.assemble([_make_candidate("id-1", "X")])
    assert context_1.total_memories == 1
    assert context_1.total_chars == 1
    assert context_1.items[0].content == "X"


def test_invalid_parameters_validation():
    """Verify invalid parameters (< 1) raise validation errors."""
    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_memories=0)

    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_memories=-1)

    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_content_chars=0)

    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_content_chars=-10)

    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_context_chars=0)

    with pytest.raises((ValidationError, ValueError)):
        ContextAssemblyConfig(max_context_chars=-100)


def test_deterministic_multiple_runs():
    """Verify multiple assembly invocations on identical input yield identical results."""
    candidates = [
        _make_candidate(f"id-{i}", f"Sample text {i * 10}", retrieval_score=1.0 / (i + 1))
        for i in range(10)
    ]
    assembler = ContextAssembler()

    results = [assembler.assemble(candidates) for _ in range(5)]

    first_dump = results[0].to_dict()
    for res in results[1:]:
        assert res.to_dict() == first_dump


def test_duck_typing_and_dict_compatibility():
    """Verify assembler works with plain dictionaries or duck-typed objects."""
    dict_cand = {
        "id": "dict-1",
        "content": "Dict content",
        "category": "task",
        "source": "imported",
        "importance": 0.7,
        "confidence": 0.8,
        "retrieval_score": 0.85,
        "hybrid_score": 0.80,
    }

    assembler = ContextAssembler()
    context = assembler.assemble([dict_cand])

    assert context.total_memories == 1
    assert context.items[0].id == "dict-1"
    assert context.items[0].content == "Dict content"
    assert context.items[0].memory_type == "task"
    assert context.items[0].source == "imported"

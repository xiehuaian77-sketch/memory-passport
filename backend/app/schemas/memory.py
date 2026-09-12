"""Pydantic schemas for Memory-related requests / responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------- Memory CRUD ----------

class MemoryCreate(BaseModel):
    memory_type: str | None = Field(
        default=None,
        description="Memory type; kept as string for extensibility.",
        pattern=r"^(preference|identity|task|context)$",
    )
    # Backward compatibility: accept old field name "category"
    category: str | None = Field(default=None, alias="category")
    key: str = Field(max_length=200)
    content: str = Field(min_length=1)
    source: str = Field(default="manual", pattern=r"^(manual|ai_extracted|imported)$")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    is_shared: bool = True
    tags: str = ""  # comma-separated


class MemoryUpdate(BaseModel):
    category: str | None = Field(
        default=None, pattern=r"^(preference|identity|task|context)$"
    )
    key: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_shared: bool | None = None
    tags: str | None = None


class MemoryOut(BaseModel):
    id: str
    user_id: str
    category: str
    key: str
    content: str
    source: str
    confidence: float
    is_shared: bool
    tags: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    embedding: list[float] | None = None

    model_config = {"from_attributes": True}


# ---------- Search ----------

class SearchQuery(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    category: str | None = None


class SearchResult(BaseModel):
    memory: MemoryOut
    score: float  # cosine similarity


# ---------- Chat ----------

class ChatMessage(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000, description="User chat message")
    history: list[ChatMessage] = Field(default_factory=list)
    agent_role: str = Field(
        default="general",
        description="Simulated agent role for cross-app demo",
    )

    model_config = {"extra": "ignore"}

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message must not be empty or whitespace only")
        return v.strip()


class ExtractedMemory(BaseModel):
    category: str
    key: str
    content: str
    confidence: float


class ChatResponse(BaseModel):
    response: str = Field(description="AI response text")
    reply: str | None = Field(
        default=None, description="Compatibility alias for response"
    )
    extracted_memories: list[ExtractedMemory] = Field(default_factory=list)
    loaded_memories: list[MemoryOut] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    def model_post_init(self, __context: Any) -> None:
        if self.reply is None:
            self.reply = self.response
        if not self.response and self.reply:
            self.response = self.reply


class ExtractedCandidate(BaseModel):
    category: str = Field(
        default="preference",
        pattern=r"^(preference|identity|task|context)$",
        description="Memory category",
    )
    key: str = Field(min_length=1, max_length=200, description="Short identifier key")
    content: str = Field(min_length=1, description="Extracted memory content")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Memory importance")
    tags: str = Field(default="", description="Comma-separated tags")
    is_shared: bool = Field(default=True, description="Whether memory is shared with agents")


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="Raw user text to extract memories from")


class ExtractResponse(BaseModel):
    raw_content: str
    candidates: list[ExtractedCandidate] = Field(default_factory=list)

# ---------- MCP ----------

class MCPPassportResponse(BaseModel):
    passport_id: str
    display_name: str
    memories: list[MemoryOut]


class MCPQueryRequest(BaseModel):
    passport_id: str
    query: str
    top_k: int = Field(default=5, ge=1, le=20)


# ---------- Import / Export ----------

class MemoryExport(BaseModel):
    memories: list[MemoryOut]
    exported_at: datetime
    passport_id: str


class MemoryImportItem(BaseModel):
    category: str = Field(pattern=r"^(preference|identity|task|context)$")
    key: str = Field(max_length=200)
    content: str = Field(min_length=1)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    tags: str = ""


# ---------- Phase 2.3D & 2.4: Semantic, Keyword & Hybrid Search ----------

class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    search_mode: str = Field(
        default="semantic",
        pattern=r"^(semantic|keyword|hybrid)$",
        description="Search mode: semantic, keyword, or hybrid",
    )

    model_config = {"extra": "ignore"}

    @field_validator("query")
    @classmethod
    def validate_query_not_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only")
        return v.strip()


class HybridSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    search_mode: str = Field(
        default="hybrid",
        pattern=r"^(semantic|keyword|hybrid)$",
        description="Search mode: semantic, keyword, or hybrid",
    )

    model_config = {"extra": "ignore"}

    @field_validator("query")
    @classmethod
    def validate_query_not_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only")
        return v.strip()


class SemanticSearchItem(BaseModel):
    id: str
    content: str
    memory_type: str
    importance: float = 0.5
    confidence: float = 1.0
    similarity: float | None = None
    keyword_score: float | None = None
    hybrid_score: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SemanticSearchResponse(BaseModel):
    items: list[SemanticSearchItem]
    query: str
    limit: int
    search_mode: str = "semantic"


# Aliases for hybrid search clarity
HybridSearchItem = SemanticSearchItem
HybridSearchResponse = SemanticSearchResponse


# ---------- Phase 2.3F: Backfill ----------

class BackfillRequest(BaseModel):
    batch_size: int = Field(default=20, ge=1, le=100)

    model_config = {"extra": "ignore"}


class BackfillResponse(BaseModel):
    total_candidates: int
    processed: int
    succeeded: int
    failed: int
    remaining: int


# ---------- Phase 2.5C: Retrieval API ----------

class MemoryRetrievalRequest(BaseModel):
    """Request payload for context retrieval (Phase 2.5C)."""

    query: str = Field(
        min_length=1, max_length=2000, description="Query string for search"
    )
    top_k: int = Field(
        default=10, ge=1, le=50, description="Max search candidates to keep in policy"
    )
    min_relevance: float = Field(
        default=0.30, ge=0.0, le=1.0, description="Minimum hybrid score"
    )
    min_importance: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum importance"
    )
    min_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum confidence"
    )
    memory_types: list[str] | None = Field(
        default=None, description="Allowed memory categories/types"
    )
    recency_half_life_days: float = Field(
        default=30.0, gt=0.0, description="Recency decay half life in days"
    )
    max_memories: int = Field(
        default=10, ge=1, description="Max memories in assembled context"
    )
    max_content_chars: int = Field(
        default=500, ge=1, description="Max characters per memory content"
    )
    max_context_chars: int = Field(
        default=4000, ge=1, description="Max total characters in context"
    )

    model_config = {"extra": "ignore"}

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only")
        return v.strip()


RetrievalRequest = MemoryRetrievalRequest

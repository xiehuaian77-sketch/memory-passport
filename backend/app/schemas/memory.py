"""Pydantic schemas for Memory-related requests / responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

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
    status: str = Field(
        default="active", pattern=r"^(active|archived|conflicted|superseded)$"
    )
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None

    @model_validator(mode="after")
    def validate_valid_time(self) -> "MemoryCreate":
        if self.valid_from is not None and self.valid_until is not None:
            if self.valid_until < self.valid_from:
                raise ValueError("valid_until cannot be earlier than valid_from")
        return self


class MemoryUpdate(BaseModel):
    category: str | None = Field(
        default=None, pattern=r"^(preference|identity|task|context)$"
    )
    key: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_shared: bool | None = None
    tags: str | None = None
    status: str | None = Field(
        default=None, pattern=r"^(active|archived|conflicted|superseded)$"
    )
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None

    @model_validator(mode="after")
    def validate_valid_time(self) -> "MemoryUpdate":
        if self.valid_from is not None and self.valid_until is not None:
            if self.valid_until < self.valid_from:
                raise ValueError("valid_until cannot be earlier than valid_from")
        return self


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
    status: str = "active"
    version: int = 1
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    superseded_by_memory_id: str | None = None

    model_config = {"from_attributes": True}


# ---------- Conflict Detection ----------

class ConflictItem(BaseModel):
    existing_memory_id: str
    existing_key: str
    existing_content: str
    conflict_type: str = Field(
        default="key_conflict",
        description="Type of conflict: 'key_conflict' | 'semantic_conflict' | 'contradiction'",
    )
    similarity: float | None = None
    recommendation: str = Field(
        default="archive_old",
        description="Suggested action: 'archive_old' | 'replace' | 'keep_both' | 'supersede' | 'merge'",
    )
    classification: str = Field(
        default="CONTRADICTION",
        description="Relation classification: 'DUPLICATE' | 'SIMILAR' | 'RELATED' | 'UPDATE' | 'SUPERSEDE' | 'CONTRADICTION' | 'UNRELATED'",
    )
    conflict_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Contradiction severity score (0.0 to 1.0)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence of assessment (0.0 to 1.0)",
    )
    user_reason: str = Field(
        default="",
        description="Concise user-facing explanation (no CoT, no system prompts)",
    )
    tier_applied: str = Field(
        default="tier_1_rules",
        description="Assessment tier applied: 'tier_1_rules' | 'tier_2_semantic' | 'tier_3_llm'",
    )


class ConflictDetectionRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    memory_type: str = Field(
        default="preference", pattern=r"^(preference|identity|task|context)$"
    )


class ConflictDetectionResponse(BaseModel):
    has_conflict: bool
    conflicts: list[ConflictItem] = Field(default_factory=list)


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
    conversation_id: str | None = Field(
        default=None, description="Optional conversation ID to append message to"
    )
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
    conversation_id: str | None = Field(
        default=None, description="Conversation ID associated with this turn"
    )
    extracted_memories: list[ExtractedMemory] = Field(default_factory=list)
    loaded_memories: list[Any] = Field(default_factory=list)

    model_config = {"extra": "ignore"}

    def model_post_init(self, __context: Any) -> None:
        if self.reply is None:
            self.reply = self.response
        if not self.response and self.reply:
            self.response = self.reply


class ConversationMessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    pass


class ConversationExtractRequest(BaseModel):
    message_ids: list[str] | None = Field(
        default=None, description="Optional list of specific message IDs to analyze"
    )


class ConversationMemoryCandidate(BaseModel):
    id: str = Field(description="Unique candidate identifier")
    memory_type: str = Field(
        default="preference",
        pattern=r"^(preference|identity|task|context)$",
        description="Memory category",
    )
    key: str = Field(min_length=1, max_length=200, description="Short identifier key")
    content: str = Field(min_length=1, description="Extracted memory content")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    reason: str = Field(default="", description="Reason for candidate extraction")
    source: str = Field(default="conversation")
    raw_content: str = Field(default="", description="Source dialogue context")
    signature: str = Field(
        default="",
        description="Cryptographic HMAC signature binding candidate to user, conversation, and exact fields",
    )


class ConversationExtractResponse(BaseModel):
    conversation_id: str
    candidates: list[ConversationMemoryCandidate] = Field(default_factory=list)


class ConversationConfirmCandidate(BaseModel):
    id: str = Field(min_length=1, description="Unique candidate identifier from extraction")
    signature: str = Field(min_length=1, description="Cryptographic HMAC signature")
    memory_type: str = Field(
        default="preference",
        pattern=r"^(preference|identity|task|context)$",
        description="Memory category",
    )
    key: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    tags: list[str] | str = Field(default_factory=list)
    raw_content: str = Field(default="")
    is_shared: bool = True

    model_config = {"extra": "ignore"}


class CandidateUserEdits(BaseModel):
    key: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    tags: str | None = None

    model_config = {"extra": "ignore"}


class ConversationConfirmRequest(BaseModel):
    candidate: ConversationConfirmCandidate
    user_edits: CandidateUserEdits | None = None

    model_config = {"extra": "ignore"}


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
    status: str | None = Field(
        default="active", description="Filter by status: active, archived, or None for all"
    )
    temporal_mode: str = Field(
        default="current",
        pattern=r"^(current|historical|any)$",
        description="Temporal retrieval mode: current (default), historical, any",
    )
    reference_time: datetime | None = Field(
        default=None,
        description="Reference point in time to evaluate validity against",
    )
    graph_enabled: bool = Field(
        default=False,
        description="Enable 1-hop relationship graph expansion as secondary retrieval signal",
    )
    graph_seed_limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Max base seeds for graph expansion (default 5, hard limit 10)",
    )
    graph_max_expanded: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Max expanded memories from graph (default 20, hard limit 50)",
    )

    model_config = {"extra": "ignore"}

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query string must not be empty or whitespace only")
        return v.strip()


RetrievalRequest = MemoryRetrievalRequest


# ---------- Phase 5.0: Supersede ----------

class SupersedeRequest(BaseModel):
    replacement_memory_id: str = Field(
        min_length=1, max_length=36, description="ID of the replacement memory"
    )
    valid_until: datetime | None = Field(
        default=None,
        description="Optional effective end time for old memory; defaults to replacement valid_from or now",
    )

    model_config = {"extra": "forbid"}

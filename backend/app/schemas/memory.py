"""Pydantic schemas for Memory-related requests / responses."""

from datetime import datetime

from pydantic import BaseModel, Field


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
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    agent_role: str = Field(
        default="general",
        description="Simulated agent role for cross-app demo",
    )


class ExtractedMemory(BaseModel):
    category: str
    key: str
    content: str
    confidence: float


class ChatResponse(BaseModel):
    reply: str
    extracted_memories: list[ExtractedMemory] = Field(default_factory=list)
    loaded_memories: list[MemoryOut] = Field(default_factory=list)
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

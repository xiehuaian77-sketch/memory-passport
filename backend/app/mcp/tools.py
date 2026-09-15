"""Registry and implementations for all standard MCP tools in Memory Passport.

Security architecture:
1. User identity is strictly derived from the authenticated request context.
2. Direct database access is strictly forbidden; all operations delegate to existing services.
3. Permanent hard delete is forbidden from MCP tools.
4. All input arguments are parsed and sanitized via Pydantic schemas.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.mcp.constants import (
    MAX_CONTEXT_CHARS,
    MAX_RELATED_LIMIT,
    MAX_SEARCH_LIMIT,
    MAX_TOOL_ARG_STRING_LENGTH,
)
from app.mcp.protocol import ToolDefinition
from app.schemas.memory import (
    ConversationConfirmCandidate,
    MemoryCreate,
    MemoryRetrievalRequest,
    MemoryUpdate,
    SemanticSearchRequest,
)
from app.repositories import conversation_repo
from app.services import (
    extraction_service,
    governance_service,
    memory_relationship_service,
    memory_service,
)
from app.services.chat_service import get_chat_service

# ---------- Input Schemas for Tools ----------

class MemorySearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    search_mode: str = Field(default="hybrid", pattern=r"^(semantic|keyword|hybrid)$")
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)


class MemoryRetrieveInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    min_relevance: float = Field(default=0.30, ge=0.0, le=1.0)
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    memory_types: list[str] | None = None
    max_context_chars: int = Field(default=MAX_CONTEXT_CHARS, ge=1, le=MAX_CONTEXT_CHARS)
    status: str | None = "active"
    temporal_mode: str = Field(default="current", pattern=r"^(current|historical|any)$")
    reference_time: datetime | None = None
    graph_enabled: bool = False
    graph_seed_limit: int = Field(default=5, ge=1, le=10)
    graph_max_expanded: int = Field(default=20, ge=1, le=50)


class MemoryGetInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)


class MemoryCreateInput(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_TOOL_ARG_STRING_LENGTH)
    memory_type: str = Field(default="preference", pattern=r"^(preference|identity|task|context)$")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: str = ""
    is_shared: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class MemoryUpdateInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)
    key: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=MAX_TOOL_ARG_STRING_LENGTH)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_shared: bool | None = None
    tags: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class MemoryArchiveInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)


class MemoryRestoreInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)


class MemorySupersedeInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)
    replacement_memory_id: str = Field(min_length=1, max_length=64)
    valid_until: datetime | None = None


class MemoryRelationshipsInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=MAX_RELATED_LIMIT)


class MemoryRelatedInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)
    direction: str = Field(default="both", pattern=r"^(outgoing|incoming|both)$")
    relationship_type: str | None = None
    confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    temporal_mode: str = Field(default="current", pattern=r"^(current|historical|any)$")
    reference_time: datetime | None = None
    limit: int = Field(default=10, ge=1, le=MAX_RELATED_LIMIT)


class MemoryExplainInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)


class MemoryHistoryInput(BaseModel):
    memory_id: str = Field(min_length=1, max_length=64)


class ConversationExtractInput(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    message_ids: list[str] | None = None


class ConversationConfirmInput(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    candidate: dict[str, Any]
    user_edits: dict[str, Any] | None = None


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_TOOL_ARG_STRING_LENGTH)
    conversation_id: str | None = None
    agent_role: str = "general"


# ---------- Tool Registry ----------

class MCPToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._schema_classes: dict[str, type[BaseModel]] = {}

    def register(
        self,
        name: str,
        description: str,
        schema_cls: type[BaseModel],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            schema = schema_cls.model_json_schema()
            tool_def = ToolDefinition(
                name=name,
                description=description,
                inputSchema=schema,
            )
            self._tools[name] = tool_def
            self._handlers[name] = handler
            self._schema_classes[name] = schema_cls
            return handler
        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.model_dump() for t in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        user: User,
        db: AsyncSession,
        caller: Any | None = None,
    ) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")

        schema_cls = self._schema_classes[name]
        handler = self._handlers[name]
        clean_args = arguments or {}
        parsed = schema_cls.model_validate(clean_args)
        import inspect
        sig = inspect.signature(handler)
        kwargs: dict[str, Any] = {"user": user, "db": db}
        if "caller" in sig.parameters:
            kwargs["caller"] = caller
        return await handler(parsed, **kwargs)


registry = MCPToolRegistry()

# ---------- Tool Implementations ----------

@registry.register(
    "memory_search",
    "Search user memories using semantic, keyword, or hybrid mode with strict user isolation.",
    MemorySearchInput,
)
async def handle_memory_search(args: MemorySearchInput, *, user: User, db: AsyncSession, caller: Any | None = None) -> dict[str, Any]:
    policy = await governance_service.get_user_policy(db, user_id=user.id)
    if not (policy.memory_enabled and policy.allow_memory_retrieval):
        return {"isError": True, "content": [{"type": "text", "text": "Memory retrieval is disabled by user policy"}]}

    req = SemanticSearchRequest(query=args.query, limit=args.limit, search_mode=args.search_mode)
    if args.search_mode == "semantic":
        results = await memory_service.semantic_search(db, user_id=user.id, query=req.query, limit=req.limit)
        items = [
            {"id": m.id, "content": m.content, "type": m.memory_type, "score": s}
            for m, s in results
        ]
    elif args.search_mode == "keyword":
        results = await memory_service.keyword_search(db, user_id=user.id, query=req.query, limit=req.limit)
        items = [
            {"id": m.id, "content": m.content, "type": m.memory_type, "score": s}
            for m, s in results
        ]
    else:
        results = await memory_service.hybrid_search(db, user_id=user.id, query=req.query, limit=req.limit)
        items = [
            {"id": r.memory.id, "content": r.memory.content, "type": r.memory.memory_type, "score": r.hybrid_score}
            for r in results
        ]
    if caller and getattr(caller, "preference_only", False):
        items = [it for it in items if it.get("type") == "preference"]
    return {"content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False)}]}


@registry.register(
    "memory_retrieve",
    "Assemble budgeted context for query with temporal evaluation and optional 1-hop graph expansion.",
    MemoryRetrieveInput,
)
async def handle_memory_retrieve(args: MemoryRetrieveInput, *, user: User, db: AsyncSession, caller: Any | None = None) -> dict[str, Any]:
    policy = await governance_service.get_user_policy(db, user_id=user.id)
    if not (policy.memory_enabled and policy.allow_memory_retrieval):
        return {"isError": True, "content": [{"type": "text", "text": "Memory retrieval is disabled by user policy"}]}

    is_pref_only = bool(caller and getattr(caller, "preference_only", False))
    req = MemoryRetrievalRequest(
        query=args.query,
        top_k=args.top_k,
        min_relevance=args.min_relevance,
        min_importance=args.min_importance,
        min_confidence=args.min_confidence,
        memory_types=["preference"] if is_pref_only else args.memory_types,
        max_context_chars=args.max_context_chars,
        status=args.status,
        temporal_mode=args.temporal_mode,
        reference_time=args.reference_time,
        graph_enabled=False if is_pref_only else args.graph_enabled,
        graph_seed_limit=args.graph_seed_limit,
        graph_max_expanded=args.graph_max_expanded,
    )
    ctx = await memory_service.retrieve_context(db, user_id=user.id, request=req)
    return {
        "content": [
            {
                "type": "text",
                "text": ctx.format_text(),
            }
        ],
        "metadata": {
            "total_memories": ctx.total_memories,
            "total_chars": ctx.total_chars,
        },
    }


@registry.register(
    "memory_get",
    "Get a single memory by ID. Returns error if not found or belongs to another user.",
    MemoryGetInput,
)
async def handle_memory_get(args: MemoryGetInput, *, user: User, db: AsyncSession, caller: Any | None = None) -> dict[str, Any]:
    mem = await memory_service.get_memory_by_id(db, memory_id=args.memory_id, user_id=user.id)
    if not mem:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}
    if caller and getattr(caller, "preference_only", False) and mem.memory_type != "preference":
        return {"isError": True, "content": [{"type": "text", "text": f"Access denied: Memory '{args.memory_id}' is not a preference"}]}
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "id": mem.id,
                    "key": mem.key,
                    "content": mem.content,
                    "category": mem.category,
                    "status": mem.status,
                    "confidence": mem.confidence,
                    "importance": mem.importance,
                    "created_at": mem.created_at.isoformat() if mem.created_at else None,
                }, ensure_ascii=False),
            }
        ]
    }


@registry.register(
    "memory_create",
    "Create a new memory for authenticated user with automatic embedding and versioning.",
    MemoryCreateInput,
)
async def handle_memory_create(args: MemoryCreateInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    mem_create = MemoryCreate(
        key=args.key,
        content=args.content,
        memory_type=args.memory_type,
        confidence=args.confidence,
        importance=args.importance,
        tags=args.tags,
        is_shared=args.is_shared,
        valid_from=args.valid_from,
        valid_until=args.valid_until,
    )
    mem = await memory_service.create_memory(db, user_id=user.id, data=mem_create, auto_embed=True)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "id": mem.id,
                    "key": mem.key,
                    "content": mem.content,
                    "status": mem.status,
                }, ensure_ascii=False),
            }
        ]
    }


@registry.register(
    "memory_update",
    "Update an existing memory with version bump and audit log.",
    MemoryUpdateInput,
)
async def handle_memory_update(args: MemoryUpdateInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    mem = await memory_service.get_memory_by_id(db, memory_id=args.memory_id, user_id=user.id)
    if not mem:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}

    update_data = MemoryUpdate(
        key=args.key or mem.key,
        content=args.content if args.content is not None else mem.content,
        confidence=args.confidence if args.confidence is not None else mem.confidence,
        is_shared=args.is_shared if args.is_shared is not None else mem.is_shared,
        tags=args.tags if args.tags is not None else mem.tags,
        valid_from=args.valid_from if args.valid_from is not None else mem.valid_from,
        valid_until=args.valid_until if args.valid_until is not None else mem.valid_until,
    )
    updated = await memory_service.update_memory(db, memory=mem, data=update_data)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"id": updated.id, "content": updated.content, "version": updated.version}, ensure_ascii=False),
            }
        ]
    }


@registry.register(
    "memory_archive",
    "Archive a memory (sets status='archived'). Excluded from normal search.",
    MemoryArchiveInput,
)
async def handle_memory_archive(args: MemoryArchiveInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    mem = await memory_service.archive_memory(db, memory_id=args.memory_id, user_id=user.id)
    if not mem:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}
    return {"content": [{"type": "text", "text": f"Memory '{mem.id}' archived successfully"}]}


@registry.register(
    "memory_restore",
    "Restore an archived memory back to active status.",
    MemoryRestoreInput,
)
async def handle_memory_restore(args: MemoryRestoreInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    mem = await memory_service.restore_memory(db, memory_id=args.memory_id, user_id=user.id)
    if not mem:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}
    return {"content": [{"type": "text", "text": f"Memory '{mem.id}' restored successfully"}]}


@registry.register(
    "memory_supersede",
    "Atomic supersede: replace old memory with new replacement memory with temporal validity cutoff.",
    MemorySupersedeInput,
)
async def handle_memory_supersede(args: MemorySupersedeInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    try:
        await memory_service.supersede_memory(
            db,
            old_memory_id=args.memory_id,
            replacement_memory_id=args.replacement_memory_id,
            user_id=user.id,
            valid_until=args.valid_until,
        )
        return {"content": [{"type": "text", "text": f"Memory '{args.memory_id}' superseded by '{args.replacement_memory_id}'"}]}
    except Exception as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}


@registry.register(
    "memory_relationships",
    "List explicit relationship edges involving this memory.",
    MemoryRelationshipsInput,
)
async def handle_memory_relationships(args: MemoryRelationshipsInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    rels = await memory_relationship_service.list_relationships_for_memory(
        db,
        current_user_id=user.id,
        memory_id=args.memory_id,
        offset=args.offset,
        limit=args.limit,
    )
    items = [
        {
            "id": r.id,
            "source_id": r.source_memory_id,
            "target_id": r.target_memory_id,
            "relationship_type": r.relationship_type,
            "confidence": r.confidence,
        }
        for r in rels
    ]
    return {"content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False)}]}


@registry.register(
    "memory_related",
    "Retrieve one-hop related memories with edge metadata, temporal filtering, and direction control.",
    MemoryRelatedInput,
)
async def handle_memory_related(args: MemoryRelatedInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    related = await memory_relationship_service.list_related_memories(
        db=db,
        current_user_id=user.id,
        memory_id=args.memory_id,
        direction=args.direction,
        relationship_type=args.relationship_type,
        confidence_min=args.confidence_min,
        temporal_mode=args.temporal_mode,
        reference_time=args.reference_time,
        offset=0,
        limit=args.limit,
    )
    items = [
        {
            "memory_id": r.memory_id,
            "content": r.content,
            "relationship_type": r.relationship_type,
            "confidence": r.relationship_confidence,
            "direction": r.direction,
        }
        for r in related
    ]
    return {"content": [{"type": "text", "text": json.dumps(items, ensure_ascii=False)}]}


@registry.register(
    "memory_explain",
    "Explain provenance, versioning, and conflict audit summary for a memory.",
    MemoryExplainInput,
)
async def handle_memory_explain(args: MemoryExplainInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    res = await governance_service.explain_memory(db, memory_id=args.memory_id, user_id=user.id)
    if not res:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}
    return {"content": [{"type": "text", "text": json.dumps(res.model_dump(), default=str, ensure_ascii=False)}]}


@registry.register(
    "memory_history",
    "Get full chronological audit trail and version revisions for a memory.",
    MemoryHistoryInput,
)
async def handle_memory_history(args: MemoryHistoryInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    res = await governance_service.get_memory_history(db, memory_id=args.memory_id, user_id=user.id)
    if not res:
        return {"isError": True, "content": [{"type": "text", "text": f"Memory '{args.memory_id}' not found"}]}
    return {"content": [{"type": "text", "text": json.dumps(res.model_dump(), default=str, ensure_ascii=False)}]}


@registry.register(
    "conversation_memory_extract",
    "Extract candidate memories from conversation history without persisting.",
    ConversationExtractInput,
)
async def handle_conversation_extract(args: ConversationExtractInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    policy = await governance_service.get_user_policy(db, user_id=user.id)
    if not (policy.memory_enabled and policy.allow_ai_extraction):
        return {"isError": True, "content": [{"type": "text", "text": "AI extraction is disabled by user policy"}]}

    conv = await conversation_repo.get_conversation(db, conversation_id=args.conversation_id, user_id=user.id)
    if not conv:
        return {"isError": True, "content": [{"type": "text", "text": "Conversation not found"}]}

    if args.message_ids:
        messages = await conversation_repo.get_messages_by_ids(db, conversation_id=args.conversation_id, message_ids=args.message_ids)
    else:
        messages = await conversation_repo.get_recent_messages(db, conversation_id=args.conversation_id, limit=20)

    candidates = await extraction_service.extract_from_conversation_messages(
        messages=messages,
        user_id=user.id,
        conversation_id=args.conversation_id,
    )
    cands_data = [c.model_dump() for c in candidates]
    return {"content": [{"type": "text", "text": json.dumps(cands_data, ensure_ascii=False)}]}


@registry.register(
    "conversation_memory_confirm",
    "Confirm an extracted candidate memory with HMAC signature integrity verification.",
    ConversationConfirmInput,
)
async def handle_conversation_confirm(args: ConversationConfirmInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    cand_obj = ConversationConfirmCandidate.model_validate(args.candidate)
    # Cryptographic integrity check: signature must be valid
    if not extraction_service.verify_candidate_signature(
        user_id=user.id,
        conversation_id=args.conversation_id,
        candidate=cand_obj,
    ):
        return {"isError": True, "content": [{"type": "text", "text": "Candidate signature is invalid or tampered"}]}

    tags_str = cand_obj.tags if isinstance(cand_obj.tags, str) else ",".join(cand_obj.tags)
    key_val = cand_obj.key or cand_obj.content[:40].replace(" ", "_").lower()

    mem_create = MemoryCreate(
        memory_type=cand_obj.memory_type,
        key=key_val[:200],
        content=cand_obj.content,
        source="ai_extracted",
        confidence=cand_obj.confidence,
        importance=cand_obj.importance,
        is_shared=cand_obj.is_shared,
        tags=tags_str,
        source_conversation_id=args.conversation_id,
    )
    created_mem = await memory_service.create_memory(db=db, user_id=user.id, data=mem_create, auto_embed=True)
    return {"content": [{"type": "text", "text": json.dumps({"id": created_mem.id, "content": created_mem.content}, ensure_ascii=False)}]}


@registry.register(
    "chat",
    "Multi-turn AI conversation with automatic memory retrieval and context injection.",
    ChatInput,
)
async def handle_chat(args: ChatInput, *, user: User, db: AsyncSession) -> dict[str, Any]:
    service = get_chat_service()
    try:
        reply = await service.chat(
            message=args.message,
            user_id=user.id,
            conversation_id=args.conversation_id,
            db=db,
        )
        return {
            "content": [{"type": "text", "text": str(reply)}],
            "metadata": {
                "conversation_id": getattr(reply, "conversation_id", None) or args.conversation_id,
            },
        }
    except Exception as exc:
        return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}

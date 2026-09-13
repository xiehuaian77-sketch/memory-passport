# Memory Passport Python SDK

Official Python client library for **Memory Passport** — the portable, controllable, traceable AI memory identity layer for autonomous agents and AI assistants.

## Highlights

- **Typed Models**: Full Pydantic v2 support with runtime validation and safe extra-field tolerance.
- **Pure Client Architecture**: Server owns all business logic, retrieval algorithms, and graph scoring. SDK is a clean, typed REST client.
- **Graph-aware Retrieval**: Seamlessly control 1-hop relationship expansion (`graph_enabled`, `graph_seed_limit`, `graph_max_expanded`).
- **Temporal Memory Support**: Query active memories, historical snapshots, or custom reference times (`temporal_mode="current" | "historical" | "any"`).
- **Hardened Security**: Zero credential persistence, zero telemetry, zero leak in exceptions or logs.
- **Safe Network Resilience**: Automatic backoff and retries exclusively on safe GET requests. Non-idempotent mutations (POST/PUT/DELETE) never duplicate.

## Installation

```bash
pip install memory-passport
```

Requirements: Python >= 3.11

## Quick Start (3 Lines)

```python
from memory_passport import MemoryPassportClient

client = MemoryPassportClient(base_url="http://localhost:8000", api_key="test-key")
memory = client.memories.create(key="pref_lang", content="User prefers Python for data scripts.")
print(memory.id, memory.content)
```

## Basic Usage

### 1. Memory CRUD & Iteration

```python
# Create memory
m = client.memories.create(
    key="pref_ide",
    content="User uses VS Code with dark theme",
    memory_type="preference",
    confidence=0.95,
    importance=0.8,
    tags=["tools", "ui"],
)

# Get & Update
mem = client.memories.get(m.id)
client.memories.update(m.id, content="User uses VS Code or Antigravity with dark theme")

# Stream / Iterate over memories
for item in client.memories.iter(category="preference", page_size=20):
    print(f"- [{item.key}] {item.content}")

# Delete
client.memories.delete(m.id)
```

### 2. Semantic, Hybrid Search & Graph-aware Retrieval

```python
# Hybrid Search
results = client.search.hybrid(query="developer tools", limit=5)
for res in results.items:
    print(res.content, res.hybrid_score)

# Context Retrieval with Graph-aware Expansion
context = client.search.retrieve(
    query="What is the user's preferred development setup?",
    max_context_chars=3000,
    graph_enabled=True,
    graph_seed_limit=5,
    graph_max_expanded=10,
    temporal_mode="current",
)
print("Budgeted Context:")
print(context.format_text())
```

### 3. Memory Relationships & Knowledge Graph

```python
# Link two memories
rel = client.graph.create_relationship(
    source_memory_id=mem1.id,
    target_memory_id=mem2.id,
    relationship_type="RELEVANT_TO",
    confidence=0.9,
)

# Discover 1-hop related memories
related = client.graph.related(
    memory_id=mem1.id,
    direction="both",
    temporal_mode="current",
)
for r in related:
    print(r.content, r.relationship_type)
```

### 4. Lifecycle & Governance

```python
# Archive & Restore
archived = client.lifecycle.archive(mem1.id)
restored = client.lifecycle.restore(mem1.id)

# Supersede old memory
client.lifecycle.supersede(mem1.id, replacement_memory_id=mem2.id)

# Governance Policy
policy = client.governance.get_policy()
client.governance.update_policy(require_confirmation=True, allow_ai_extraction=True)
```

### 5. Conversations & Chat

```python
# Multi-turn chat with automatic memory retrieval
reply = client.chat.chat(
    message="What editor do I usually write Python in?",
    conversation_id="conv-123",
)
print("AI:", reply.response)
```

## Exception Handling

The SDK maps all HTTP and network states to a clean, typed exception hierarchy:

```python
from memory_passport.exceptions import (
    AuthenticationError,
    ConflictError,
    MemoryPassportError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

try:
    client.memories.get("non-existent-id")
except NotFoundError as e:
    print(f"Resource not found: {e.message}")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except NetworkError as e:
    print(f"Connection error: {e}")
except MemoryPassportError as e:
    print(f"General SDK error: {e}")
```

## Security & Privacy Guarantee

1. **No Telemetry**: SDK does not phone home or transmit memory content to external analytics.
2. **Credential Sanitization**: `repr(client)` and exception traces automatically redact API keys and access tokens.
3. **No File Persistence**: Tokens and credentials exist purely in-memory during application lifetime.

## License

MIT License.

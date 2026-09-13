"""Tests for conversations and chat resources."""

def test_conversations_lifecycle(mock_handler, mock_client):
    mock_handler.register("POST", "/api/conversations", status_code=201, json_data={
        "id": "conv-1",
        "user_id": "usr-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "messages": [],
    })
    conv = mock_client.conversations.create()
    assert conv.id == "conv-1"

    mock_handler.register("GET", "/api/conversations/conv-1", status_code=200, json_data={
        "id": "conv-1",
        "user_id": "usr-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "messages": [],
    })
    fetched = mock_client.conversations.get("conv-1")
    assert fetched.id == "conv-1"

    mock_handler.register("DELETE", "/api/conversations/conv-1", status_code=204)
    mock_client.conversations.delete("conv-1")
    assert mock_handler.requests[-1].method == "DELETE"


def test_conversation_extract_and_confirm(mock_handler, mock_client):
    mock_handler.register("POST", "/api/conversations/conv-1/extract-memory", status_code=200, json_data={
        "conversation_id": "conv-1",
        "candidates": [
            {
                "id": "cand-1",
                "memory_type": "preference",
                "key": "editor",
                "content": "User uses VS Code",
                "importance": 0.8,
                "confidence": 0.95,
                "tags": ["editor"],
                "signature": "valid_hmac_sig",
            }
        ],
    })
    ext = mock_client.conversations.extract_memory("conv-1")
    assert len(ext.candidates) == 1
    assert ext.candidates[0].signature == "valid_hmac_sig"

    mock_handler.register("POST", "/api/conversations/conv-1/confirm-memory", status_code=201, json_data={
        "id": "mem-confirmed",
        "user_id": "usr-1",
        "key": "editor",
        "content": "User uses VS Code",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })
    mem = mock_client.conversations.confirm_memory(
        "conv-1",
        candidate={
            "id": "cand-1",
            "signature": "valid_hmac_sig",
            "content": "User uses VS Code",
        },
    )
    assert mem.id == "mem-confirmed"


def test_chat_resource(mock_handler, mock_client):
    mock_handler.register("POST", "/api/chat", status_code=200, json_data={
        "response": "Hello! I remember you like Python.",
        "reply": "Hello! I remember you like Python.",
        "conversation_id": "conv-1",
        "extracted_memories": [],
        "loaded_memories": [],
    })
    reply = mock_client.chat.chat("What do I like?", conversation_id="conv-1")
    assert reply.response == "Hello! I remember you like Python."
    assert reply.conversation_id == "conv-1"

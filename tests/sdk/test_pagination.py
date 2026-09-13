"""Tests for pagination and iterator."""



def test_memories_iter_across_pages(mock_handler, mock_client):
    page_1 = [
        {
            "id": f"mem-{i}",
            "user_id": "u1",
            "key": f"k{i}",
            "content": f"c{i}",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        for i in range(1, 3)
    ]
    page_2 = [
        {
            "id": "mem-3",
            "user_id": "u1",
            "key": "k3",
            "content": "c3",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]

    def dynamic_handler(request):
        url = str(request.url)
        if "offset=0" in url:
            data = page_1
        elif "offset=2" in url:
            data = page_2
        else:
            data = []
        import json
        return httpx.Response(200, headers={"content-type": "application/json"}, content=json.dumps(data).encode("utf-8"))

    import httpx
    mock_handler._default_handler = dynamic_handler

    items = list(mock_client.memories.iter(page_size=2))
    assert len(items) == 3
    assert [m.id for m in items] == ["mem-1", "mem-2", "mem-3"]

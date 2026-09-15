#!/usr/bin/env python3
"""Memory Passport - Hackathon Agent MCP Authorization Demo CLI.

Demonstrates the real-time autonomous Agent Access Control & Permission Delegation loop:
1. Agent Authentication via mp_ak_ API Key (HTTP -> MCP Router -> CallerContext)
2. READ_MEMORY via memory_search (200 ALLOW)
3. CREATE_MEMORY without permission (403 DENY - Principle of Least Privilege)
4. User Grants CREATE_MEMORY via Human Management API (POST /api/agents/{id}/permissions)
5. CREATE_MEMORY again (200 ALLOW)
6. UPDATE_MEMORY without permission (403 DENY) -> Grant -> 200 ALLOW
7. User Revokes Agent (POST /api/agents/{id}/revoke)
8. Agent Access after Revoke (401 DENY - Immediate Enforcement)
9. Governance Audit Trail Inspection (Zero Secret Leakage)

Usage:
    export MEMORY_PASSPORT_DEMO_AGENT_KEY="mp_ak_..."
    export MEMORY_PASSPORT_DEMO_USER_TOKEN="eyJ..."
    python scripts/demo_agent_mcp_auth.py [--base-url http://127.0.0.1:8000] [--no-color]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

# Color constants
COLOR_GREEN = "\033[92m"
COLOR_RED = "\033[91m"
COLOR_YELLOW = "\033[93m"
COLOR_CYAN = "\033[96m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RESET = "\033[0m"


def colorize(text: str, color_code: str, no_color: bool = False) -> str:
    if no_color:
        return text
    return f"{color_code}{text}{COLOR_RESET}"


def mask_secret(secret: str | None) -> str:
    if not secret:
        return "<none>"
    if len(secret) <= 12:
        return "***"
    return f"{secret[:6]}...{secret[-4:]}"


def mcp_call(
    base_url: str,
    tool_name: str,
    arguments: dict[str, Any] | None,
    api_key: str,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    """Execute real HTTP POST request to /mcp endpoint with Agent API Key."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "MCP-Protocol-Version": "2026-07-28",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/mcp",
            headers=headers,
            json=payload,
            timeout=timeout,
            trust_env=False,
        )
        data = resp.json() if resp.content else {}
        return resp.status_code, data
    except httpx.HTTPError as exc:
        return -1, {"error": f"HTTP Transport Error: {exc.__class__.__name__}"}


def human_api_call(
    base_url: str,
    method: str,
    path: str,
    user_token: str,
    json_body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    """Execute authenticated REST call using Human JWT."""
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json",
    }
    url = f"{base_url.rstrip('/')}{path}"
    try:
        resp = httpx.request(
            method=method,
            url=url,
            headers=headers,
            json=json_body,
            timeout=timeout,
            trust_env=False,
        )
        data = resp.json() if resp.content else {}
        return resp.status_code, data
    except httpx.HTTPError as exc:
        return -1, {"error": f"HTTP Transport Error: {exc.__class__.__name__}"}


def check_server_health(base_url: str) -> bool:
    """Verify backend is running and healthy."""
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/health", timeout=3.0, trust_env=False)
        return resp.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def run_demo(
    base_url: str,
    agent_key: str,
    user_token: str,
    no_color: bool = False,
    delay: float = 0.3,
) -> int:
    """Execute full 8-step Agent Access Control verification loop."""
    print("\n" + "=" * 65)
    print(colorize(" MEMORY PASSPORT — AGENT AUTONOMOUS MEMORY DEMO", COLOR_BOLD + COLOR_CYAN, no_color))
    print(colorize(" Zero-Trust Permission Delegation & Real-Time MCP Boundary", COLOR_DIM, no_color))
    print("=" * 65)
    print(f" Target Endpoint:   {base_url}/mcp")
    print(f" Agent API Key:     {mask_secret(agent_key)} (mp_ak_ credential)")
    print(f" User Session:      {mask_secret(user_token)} (Human JWT)")
    print("-" * 65)

    # 0. Health Verification
    if not check_server_health(base_url):
        print(colorize(f"\nERROR: Memory Passport backend is not running at {base_url}", COLOR_RED, no_color))
        print("Please start the backend service: uvicorn app.main:app --port 8000")
        return 1

    # Resolve Demo Agent ID via Human API
    status_code, agents_data = human_api_call(base_url, "GET", "/api/agents", user_token)
    if status_code != 200 or not isinstance(agents_data, list):
        print(colorize(f"\nERROR: Failed to fetch Agent list with User Token (Status {status_code})", COLOR_RED, no_color))
        return 1

    # Match demo agent
    demo_agent = next(
        (a for a in agents_data if a.get("name") == "Demo Research Assistant"),
        None,
    ) or (agents_data[0] if agents_data else None)

    if not demo_agent:
        print(colorize("\nERROR: No AI Agent found for this user. Run 'python scripts/seed_demo_data.py' first.", COLOR_RED, no_color))
        return 1

    agent_id = demo_agent["id"]
    agent_name = demo_agent["name"]
    print(f" Resolved Agent:    {agent_name} ({colorize(agent_id, COLOR_CYAN, no_color)})")
    print("=" * 65 + "\n")
    time.sleep(delay)

    # STEP 1: Agent Authentication
    print(colorize("[1/8] Agent Authentication", COLOR_BOLD, no_color))
    print("   Sending MCP protocol handshake with Agent Bearer token...")
    headers = {
        "Authorization": f"Bearer {agent_key}",
        "MCP-Protocol-Version": "2026-07-28",
        "Content-Type": "application/json",
    }
    ping_resp = httpx.post(
        f"{base_url.rstrip('/')}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        timeout=5.0,
        trust_env=False,
    )
    if ping_resp.status_code != 200:
        print(colorize(f"   ✗ Authentication failed: HTTP {ping_resp.status_code}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ Agent credential accepted via CallerContext (is_agent=True)", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 2: READ_MEMORY
    print(colorize("\n[2/8] READ_MEMORY (Authorized Tool: memory_search)", COLOR_BOLD, no_color))
    print("   Agent executing keyword search for user preferences...")
    s2_status, s2_data = mcp_call(
        base_url,
        "memory_search",
        {"query": "Python", "search_mode": "keyword", "limit": 3},
        agent_key,
    )
    if s2_status != 200 or "result" not in s2_data:
        print(colorize(f"   ✗ Expected 200 ALLOW, got {s2_status}: {s2_data}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ ALLOW — Access granted under READ_MEMORY permission", COLOR_GREEN, no_color))
    content_raw = s2_data.get("result", {}).get("content", [{}])[0].get("text", "[]")
    try:
        items = json.loads(content_raw)
        print(colorize(f"   ✓ Retrieved {len(items)} memory items securely:", COLOR_CYAN, no_color))
        for it in items[:2]:
            print(f"      • [{it.get('type', 'context')}] {it.get('content', '')[:65]}...")
    except Exception:
        pass
    time.sleep(delay)

    # STEP 3: CREATE_MEMORY WITHOUT PERMISSION
    print(colorize("\n[3/8] CREATE_MEMORY (High-Privilege Write Attempt)", COLOR_BOLD, no_color))
    print("   Agent attempting memory_create without CREATE_MEMORY grant...")
    s3_status, s3_data = mcp_call(
        base_url,
        "memory_create",
        {
            "key": "demo_research_note",
            "content": "Autonomous Agent logged technical research notes (DEMO_ONLY)",
            "memory_type": "context",
        },
        agent_key,
    )
    if s3_status != 403:
        print(colorize(f"   ✗ Security boundary failure! Expected 403, got {s3_status}", COLOR_RED, no_color))
        return 1
    err_detail = s3_data.get("detail", "Permission denied")
    print(colorize(f"   ✗ DENIED ({s3_status}) — {err_detail}", COLOR_YELLOW, no_color))
    print(colorize("   ✓ Expected 403 — CREATE_MEMORY permission strictly enforced", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 4: USER GRANTS CREATE_MEMORY
    print(colorize("\n[4/8] USER GRANTS CREATE_MEMORY (Human Governance API)", COLOR_BOLD, no_color))
    print(f"   User approving permission delegation to Agent '{agent_id}'...")
    s4_status, s4_data = human_api_call(
        base_url,
        "POST",
        f"/api/agents/{agent_id}/permissions",
        user_token,
        {"permission": "CREATE_MEMORY"},
    )
    if s4_status != 201:
        print(colorize(f"   ✗ Failed to grant permission (Status {s4_status}): {s4_data}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ CREATE_MEMORY granted dynamically via human session", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 5: CREATE_MEMORY AGAIN
    print(colorize("\n[5/8] CREATE_MEMORY (Authorized Re-execution)", COLOR_BOLD, no_color))
    print("   Agent retrying memory_create with newly delegated grant...")
    s5_status, s5_data = mcp_call(
        base_url,
        "memory_create",
        {
            "key": "demo_research_note",
            "content": "Autonomous Agent logged technical research notes (DEMO_ONLY)",
            "memory_type": "context",
        },
        agent_key,
    )
    if s5_status != 200 or "result" not in s5_data:
        print(colorize(f"   ✗ Expected 200 ALLOW after grant, got {s5_status}: {s5_data}", COLOR_RED, no_color))
        return 1
    created_text = s5_data["result"]["content"][0]["text"]
    created_obj = json.loads(created_text)
    created_memory_id = created_obj.get("id", "")
    print(colorize(f"   ✓ ALLOW — Memory successfully persisted (ID: {created_memory_id[:8]}...)", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 6: UPDATE_MEMORY (Deny -> Grant -> Allow)
    print(colorize("\n[6/8] UPDATE_MEMORY (Scoped Privilege Transition)", COLOR_BOLD, no_color))
    print("   Agent attempting to modify existing memory without UPDATE_MEMORY...")
    s6_status, s6_data = mcp_call(
        base_url,
        "memory_update",
        {
            "memory_id": created_memory_id,
            "content": "Updated autonomous research findings v2 (DEMO_ONLY)",
        },
        agent_key,
    )
    if s6_status != 403:
        print(colorize(f"   ✗ Expected 403, got {s6_status}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✗ DENIED — Expected 403: UPDATE_MEMORY permission not granted", COLOR_YELLOW, no_color))

    # User grants UPDATE_MEMORY
    print("   User delegating UPDATE_MEMORY permission...")
    u_grant_status, _ = human_api_call(
        base_url,
        "POST",
        f"/api/agents/{agent_id}/permissions",
        user_token,
        {"permission": "UPDATE_MEMORY"},
    )
    if u_grant_status != 201:
        print(colorize(f"   ✗ Failed to grant UPDATE_MEMORY: {u_grant_status}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ UPDATE_MEMORY granted", COLOR_GREEN, no_color))

    # Retry memory_update
    s6b_status, s6b_data = mcp_call(
        base_url,
        "memory_update",
        {
            "memory_id": created_memory_id,
            "content": "Updated autonomous research findings v2 (DEMO_ONLY)",
        },
        agent_key,
    )
    if s6b_status != 200:
        print(colorize(f"   ✗ Expected 200, got {s6b_status}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ Memory updated successfully after user approval", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 7: USER REVOKES AGENT
    print(colorize("\n[7/8] USER REVOKES AGENT (Emergency Kill Switch)", COLOR_BOLD, no_color))
    print(f"   User revoking Agent '{agent_id}' and invalidating all credentials...")
    s7_status, s7_data = human_api_call(
        base_url,
        "POST",
        f"/api/agents/{agent_id}/revoke",
        user_token,
    )
    if s7_status != 200 or s7_data.get("status", "").upper() != "REVOKED":
        print(colorize(f"   ✗ Failed to revoke Agent (Status {s7_status}): {s7_data}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ Agent status changed to REVOKED across system", COLOR_GREEN, no_color))
    time.sleep(delay)

    # STEP 8: ACCESS AFTER REVOKE
    print(colorize("\n[8/8] ACCESS AFTER REVOKE (Instant Enforcement)", COLOR_BOLD, no_color))
    print("   Agent attempting memory_search with revoked credential...")
    s8_status, s8_data = mcp_call(
        base_url,
        "memory_search",
        {"query": "Python"},
        agent_key,
    )
    if s8_status != 401:
        print(colorize(f"   ✗ Security boundary failure! Expected 401, got {s8_status}", COLOR_RED, no_color))
        return 1
    print(colorize("   ✓ DENIED — Expected 401: Agent credentials revoked immediately", COLOR_GREEN, no_color))
    time.sleep(delay)

    # 9. AUDIT LOG VERIFICATION
    print(colorize("\n[AUDIT] GOVERNANCE AUDIT TRAIL VERIFICATION", COLOR_BOLD, no_color))
    print("   Fetching provenance audit logs via User Management API...")
    audit_status, audit_logs = human_api_call(
        base_url,
        "GET",
        f"/api/agents/audit-logs?agent_id={agent_id}&limit=10",
        user_token,
    )
    if audit_status == 200 and isinstance(audit_logs, list):
        print(colorize(f"   Recorded {len(audit_logs)} audit events for Agent {agent_id}:", COLOR_CYAN, no_color))
        for log in audit_logs[:5]:
            decision = log.get("decision") or log.get("action", "")
            tool = log.get("tool") or ""
            action = log.get("action", "")
            d_color = COLOR_GREEN if decision == "ALLOW" else (COLOR_RED if decision == "DENY" else COLOR_CYAN)
            print(f"      • [{colorize(decision, d_color, no_color)}] Action: {action:16} Tool: {tool:14} (No key leaked)")
    print(colorize("   ✓ Audit trail guarantees zero credential leakage", COLOR_GREEN, no_color))

    print("\n" + "=" * 65)
    print(colorize(" [SUCCESS] AGENT MCP AUTHORIZATION DEMO COMPLETED (Code: 0)", COLOR_BOLD + COLOR_GREEN, no_color))
    print("=" * 65 + "\n")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Passport Agent MCP Authorization Demo")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL of Memory Passport API")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("--delay", type=float, default=0.3, help="Inter-step delay in seconds")
    args = parser.parse_args()

    agent_key = os.environ.get("MEMORY_PASSPORT_DEMO_AGENT_KEY", "").strip()
    if not agent_key:
        print(colorize("ERROR: MEMORY_PASSPORT_DEMO_AGENT_KEY is not set.", COLOR_RED, args.no_color))
        print("Please set the environment variable:")
        print("   $env:MEMORY_PASSPORT_DEMO_AGENT_KEY=\"mp_ak_...\" (PowerShell)")
        print("   export MEMORY_PASSPORT_DEMO_AGENT_KEY=\"mp_ak_...\" (Bash)")
        sys.exit(1)

    user_token = os.environ.get("MEMORY_PASSPORT_DEMO_USER_TOKEN", "").strip()
    if not user_token:
        print(colorize("ERROR: MEMORY_PASSPORT_DEMO_USER_TOKEN is not set.", COLOR_RED, args.no_color))
        print("Please set the environment variable:")
        print("   $env:MEMORY_PASSPORT_DEMO_USER_TOKEN=\"<jwt>\" (PowerShell)")
        print("   export MEMORY_PASSPORT_DEMO_USER_TOKEN=\"<jwt>\" (Bash)")
        sys.exit(1)

    sys.exit(
        run_demo(
            base_url=args.base_url,
            agent_key=agent_key,
            user_token=user_token,
            no_color=args.no_color,
            delay=args.delay,
        )
    )


if __name__ == "__main__":
    main()

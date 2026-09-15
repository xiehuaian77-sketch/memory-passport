# Memory Passport — Hackathon Live Demo Guide

Complete walkthrough and operational guide for running the live **Memory Passport** Hackathon demonstration.

---

## 1. 30-Second Elevator Pitch

> **"Traditional AI agents suffer from memory silos and excessive privilege: they either forget everything across sessions, or receive a blank-check API key with full database access. Memory Passport provides user-owned long-term memory infrastructure for AI agents. Users anchor their identity with Web3, delegate granular permissions to autonomous agents, and govern agent access in real time via standard MCP protocols with instant revocation."**

---

## 2. One-Command Start

From the project root directory:

```bash
python scripts/start_demo.py
```

### What happens automatically:
1. **Runtime Verification**: Checks Python (>= 3.10), Node.js, and npm.
2. **Backend Startup**: Launches FastAPI on `http://127.0.0.1:8000` and waits for `/health`.
3. **Frontend Startup**: Launches Next.js dev server on `http://localhost:3000` and waits for compilation.
4. **Data Seeding**: Idempotently creates demo user (`demo@memorypassport.ai`), 10 memory items, 5 graph relationships, evaluation test cases, and registers `Demo Research Assistant` with initial `READ_MEMORY` permission.
5. **MCP Probe**: Validates JSON-RPC 2.0 handshake and 15 MCP tools on `http://127.0.0.1:8000/mcp`.
6. **Live Dashboard**: Displays all endpoint URLs and instructions.

*(Keep this terminal window open during the demo.)*

---

## 3. Human Governance Console

Open your browser to:

👉 **[http://localhost:3000/identity](http://localhost:3000/identity)**

Login credentials:
- **Email**: `demo@memorypassport.ai`
- **Password**: `demo123456`

### Key UI Features:
- **Identity / Passport Card**: Displays Web3 Wallet address / User ID anchor.
- **AI Agent Access Control Panel**: Displays registered AI agents, their active/revoked status, and active permission tags (`READ_MEMORY`).
- **Dynamic Governance Buttons**: Delegate permissions (`CREATE_MEMORY`, `UPDATE_MEMORY`) or execute the **Revoke Agent** emergency kill switch.

Additional observation views:
- **Memory Dashboard**: `http://localhost:3000/dashboard` (Inspect 10 seeded memories & graph topology)
- **Evaluation Console**: `http://localhost:3000/dashboard/evaluation` (Quality benchmarks & retrieval metrics)

---

## 4. Live Agent MCP Authorization Demo

Open a **second terminal** and run the autonomous agent demo script:

```bash
python scripts/demo_agent_mcp_auth.py
```

This script executes real HTTP requests over the standard Model Context Protocol (`/mcp`), simulating an autonomous agent interacting with the user's sovereign memory.

---

## 5. Expected Authorization Flow (8 Steps)

| Step | Action | Endpoint / Tool | Expected Result | Technical Mechanism |
| :--- | :--- | :--- | :--- | :--- |
| **1/8** | Agent Authentication | `POST /mcp` (`tools/list`) | **200 OK** | Bearer token (`mp_ak_...`) mapped to `CallerContext(is_agent=True)` |
| **2/8** | `READ_MEMORY` | `POST /mcp` (`memory_search`) | **200 OK (ALLOW)** | Permitted by initial `READ_MEMORY` grant; returns user context |
| **3/8** | High-Privilege Write | `POST /mcp` (`memory_create`) | **403 FORBIDDEN** | Blocked! Agent lacks `CREATE_MEMORY` permission |
| **4/8** | Human Delegation | `POST /api/agents/{id}/permissions` | **201 CREATED** | Human user dynamically delegates `CREATE_MEMORY` via session API |
| **5/8** | Authorized Re-execution | `POST /mcp` (`memory_create`) | **200 OK (ALLOW)** | Memory successfully persisted with unique UUID |
| **6/8** | Scoped Privilege Transition | `POST /mcp` (`memory_update`) | **403 -> 200** | Initial attempt denied (403); human grants `UPDATE_MEMORY`; second attempt succeeds |
| **7/8** | Emergency Kill Switch | `POST /api/agents/{id}/revoke` | **200 OK** | Human revokes agent; agent status transitions to `REVOKED` |
| **8/8** | Access After Revocation | `POST /mcp` (`memory_search`) | **401 UNAUTHORIZED** | Instant enforcement; all subsequent agent requests rejected |

---

## 6. Audit Trail Verification

The demo script concludes with an audit log inspection:

```text
[AUDIT] GOVERNANCE AUDIT TRAIL VERIFICATION
   Fetching provenance audit logs via User Management API...
   Recorded 10 audit events for Agent ag_61e2...
      • [AGENT_REVOKE] Action: AGENT_REVOKE     Tool:
      • [ALLOW] Action: AGENT_ACCESS     Tool: memory_update
      • [PERMISSION_GRANT] Action: PERMISSION_GRANT Tool:
      • [DENY] Action: AGENT_ACCESS     Tool: memory_update
      • [ALLOW] Action: AGENT_ACCESS     Tool: memory_create
   ✓ Audit trail guarantees zero credential leakage
```

Every action (ALLOW, DENY, GRANT, REVOKE) is recorded with timestamps, actor IDs, and tool names. **No raw API keys or passwords are ever stored in audit logs.**

---

## 7. Graceful Shutdown

When the demonstration is finished:
- Press **`Ctrl+C`** in the `scripts/start_demo.py` terminal window.
- The launcher catches `SIGINT` and automatically terminates both the FastAPI uvicorn process and the Next.js dev process.
- All ports (`8000` and `3000`) are cleanly freed with zero orphaned background processes.

---

## 8. Troubleshooting Matrix

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **Port 8000 occupied** | A previous backend or another service is listening on port 8000. | Check if it is Memory Passport; if so, `start_demo.py` automatically reuses it. Otherwise, terminate the occupying process:<br>`powershell -Command "Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force"` |
| **Port 3000 occupied** | Another web server is using port 3000. | Free port 3000:<br>`powershell -Command "Get-Process -Id (Get-NetTCPConnection -LocalPort 3000).OwningProcess | Stop-Process -Force"` |
| **Node.js / npm missing** | Node.js is not in the system `PATH`. | Install Node.js v18+ from [nodejs.org](https://nodejs.org/) and verify with `node -v` and `npm -v`. |
| **Backend unavailable** | Dependencies missing or database locked. | Run `cd backend && pip install -r requirements.txt` and verify `python -m uvicorn app.main:app --port 8000`. |
| **Demo Agent key missing** | Database was wiped or seed failed to parse. | Run `python scripts/seed_demo_data.py`. The script will output the freshly minted `mp_ak_` key or reuse the existing agent. |
| **Agent in REVOKED state** | A previous run executed the kill switch. | Run `python scripts/seed_demo_data.py`. It detects the revoked demo agent and automatically reactivates it to `ACTIVE` with `READ_MEMORY`. |
| **Frontend compilation slow** | Next.js first build on Windows can take 15-30s. | `start_demo.py` allows a 45-second timeout window. Wait for compilation dots to finish, or pre-warm by running `npm run build` once in `frontend/`. |

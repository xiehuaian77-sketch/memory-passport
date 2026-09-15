# Memory Passport — 3–5 Minute Hackathon Presentation Script

A spoken-word, step-by-step presentation script designed for live Hackathon judges and audience demonstrations.

---

## Stage Setup & Timing Overview

- **Presenter Setup**:
  - Screen 1 (Left / Browser): `http://localhost:3000/identity` (Human Console)
  - Screen 2 (Right / Terminal): Ready with `python scripts/demo_agent_mcp_auth.py`
- **Total Duration**: 4 Minutes 30 Seconds

---

## 0:00 – 0:30 | The Problem & The Mission

*(Speaker faces judges; gestures toward the title slide or initial screen)*

> **"Hello judges! Today, every autonomous AI agent—whether in Cursor, Claude, or a custom workflow—faces a fundamental dilemma: memory silos and data insecurity.**
>
> **Right now, agents either forget everything the moment a session closes, or developers hand them a full-access database key that lets them read, overwrite, and leak everything. Users have zero real ownership over their personal context.**
>
> **We built Memory Passport: the user-owned long-term memory infrastructure for AI agents. We give humans true cryptographic ownership of their memory, with fine-grained permission delegation and real-time MCP access boundaries."**

---

## 0:30 – 1:00 | Human Sovereign Identity

*(Speaker points to Browser on Left: `http://localhost:3000/identity`)*

> **"Here is the Memory Passport Human Console.
>
> In the top panel, you see the user's sovereign identity card. Rather than being trapped in a proprietary cloud silo, the user's passport is anchored cryptographically via their Web3 wallet or Passkey.
>
> This establishes root ownership. The memory database belongs to the human, not the LLM vendor.
>
> Down below, you see the AI Agent Access Control Panel. Here, the user registers external autonomous agents as subordinate entities. Notice our agent today: 'Demo Research Assistant'. It has its own dedicated credential, and currently has only one permission tag: `READ_MEMORY`."**

---

## 1:00 – 1:40 | Autonomous Agent Handshake & READ_MEMORY

*(Speaker switches focus to Terminal on Right; launches demo)*

```bash
python scripts/demo_agent_mcp_auth.py
```

> **"Now, let's watch what happens when an external agent interacts with the user's memory over the standard Model Context Protocol.
>
> In Step 1, the agent sends its Bearer token to `POST /mcp`. The server maps this to an isolated `CallerContext`, verifying that it is an active agent.
>
> In Step 2, the agent calls `memory_search` to look up the user's technical preferences.
> Because the user granted `READ_MEMORY`, the server responds with **HTTP 200 ALLOW**. The agent securely retrieves the user's coding background and framework preferences."**

---

## 1:40 – 2:20 | Zero-Trust Boundary: CREATE_MEMORY Denied (403)

*(Speaker pauses and highlights the bright red/yellow DENIED message in terminal)*

> **"Now, look at Step 3. The agent has just finished an analysis and attempts to write a new memory into the user's database using `memory_create`.
>
> In traditional setups, this write would quietly succeed. But look at our console: **HTTP 403 Forbidden!**
>
> Our authorization gateway intercepts the tool execution before it ever touches the database. The agent was granted `READ_MEMORY`, not write access. The system strictly enforces the principle of least privilege."**

---

## 2:20 – 3:00 | Dynamic Human Delegation & Authorized Re-execution

*(Speaker switches back to Browser, clicks Grant, then watches Step 4 & 5)*

> **"So how does the agent get write access? The human user must explicitly delegate it.
>
> In Step 4, the user issues a dynamic permission delegation via the governance API, granting `CREATE_MEMORY`.
>
> In Step 5, the agent retries the exact same `memory_create` call. Look at the result: **HTTP 200 ALLOW!** The memory is now persisted with a unique UUID.
> No server restart, no token rotation, no manual config file editing—instant, policy-driven authorization."**

---

## 3:00 – 3:30 | Scoped Privilege Transition (UPDATE_MEMORY)

*(Speaker points to Step 6 output)*

> **"In Step 6, we demonstrate scoped privilege isolation. Even though the agent now has read and create permissions, when it attempts to modify existing memories via `memory_update`, it is again blocked with **HTTP 403** until the user explicitly delegates `UPDATE_MEMORY`.
>
> Once approved, the update completes successfully. Every capability must be earned."**

---

## 3:30 – 4:00 | The Emergency Kill Switch (Instant Revoke)

*(Speaker emphasizes the emergency kill switch feature)*

> **"What happens if an agent goes rogue, experiences prompt injection, or completes its project?
>
> In Step 7, the user hits the emergency red button: 'Revoke Agent'.
>
> Immediately, in Step 8, the agent attempts to read memory again. Look at the screen: **HTTP 401 Unauthorized!**
>
> The agent is revoked across the entire system. Its credentials are dead on arrival. Access is halted in under 5 milliseconds."**

---

## 4:00 – 4:30 | Complete Audit Trail & Conclusion

*(Speaker highlights the final audit table output in the terminal)*

> **"Finally, look at the governance audit trail. Every single action—the handshake, the reads, the 403 blocks, the dynamic grant, and the emergency revocation—is recorded with timestamps, tool names, and actor IDs. Crucially, zero API keys or secrets are ever leaked into logs.
>
> In summary, Memory Passport brings three simple truths to AI agent infrastructure:
>
> **1. My data is mine.**
> **2. Agents only get the permissions I give them.**
> **3. I can revoke access at any time.**
>
> Thank you! We welcome any questions from the judges."**

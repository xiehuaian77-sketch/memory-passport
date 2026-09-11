"""AI service — adapter layer over any OpenAI-compatible chat completion API.

Provides:
  1. Memory-augmented chat (inject user memories into system prompt).
  2. Memory extraction from conversations.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.schemas.memory import ExtractedMemory

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Please configure it in your .env file."
            )
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

AGENT_ROLES: dict[str, str] = {
    "general": "你是一个通用 AI 助手。",
    "code_assistant": "你是一个编程助手，擅长代码调试和架构设计。",
    "writing_coach": "你是一个写作教练，帮助用户提升表达能力。",
    "research_helper": "你是一个学术研究助手，擅长文献综述和分析。",
}


def _build_system_prompt(
    memories_text: str,
    agent_role: str = "general",
) -> str:
    """Build a system prompt that injects user memories."""
    role_desc = AGENT_ROLES.get(agent_role, AGENT_ROLES["general"])

    return f"""{role_desc}

以下是关于当前用户的 Memory Passport 记忆信息。请根据这些信息个性化你的回答：

{memories_text}

重要规则：
- 按照用户的语言偏好回答（如果记忆中有说明）。
- 按照用户的回答风格偏好回答（如简洁、详细等）。
- 如果记忆中有用户当前项目/任务信息，可以主动关联。
- 不要直接复述记忆内容，自然地融入回答中。
"""


def _format_memories(memories: list[dict]) -> str:
    """Format memory dicts into readable text for the system prompt."""
    if not memories:
        return "（当前用户尚无记忆记录）"

    sections: dict[str, list[str]] = {}
    for m in memories:
        cat = m.get("category", "other")
        line = f"- {m['key']}: {m['content']} (可信度: {m.get('confidence', 1.0):.0%}, 来源: {m.get('source', 'unknown')})"
        sections.setdefault(cat, []).append(line)

    parts = []
    cat_labels = {
        "preference": "## 用户偏好",
        "identity": "## 用户身份",
        "task": "## 当前任务",
        "context": "## 上下文",
    }
    for cat, lines in sections.items():
        label = cat_labels.get(cat, f"## {cat}")
        parts.append(label + "\n" + "\n".join(lines))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chat with memory
# ---------------------------------------------------------------------------

async def chat_with_memory(
    message: str,
    history: list[dict],
    memories: list[dict],
    agent_role: str = "general",
) -> str:
    """Send a chat completion request with memory-augmented system prompt."""
    client = _get_client()

    memories_text = _format_memories(memories)
    system_prompt = _build_system_prompt(memories_text, agent_role)

    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
    )

    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Memory extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """分析以下用户消息和 AI 回复，提取可能的用户记忆信息。

用户消息: {user_msg}
AI 回复: {ai_reply}

请提取用户偏好、身份信息、当前任务、上下文等。
以 JSON 数组格式返回，每个元素包含:
- category: "preference" | "identity" | "task" | "context"
- key: 简短的键名（如 "language_preference"）
- content: 记忆内容
- confidence: 0.0 到 1.0 之间的可信度

如果没有可提取的记忆，返回空数组 []。
只返回 JSON，不要其他文字。"""


async def extract_memories(
    user_msg: str,
    ai_reply: str,
) -> list[ExtractedMemory]:
    """Extract potential memories from a conversation turn."""
    client = _get_client()

    prompt = EXTRACTION_PROMPT.format(user_msg=user_msg, ai_reply=ai_reply)

    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1024,
    )

    raw = resp.choices[0].message.content or "[]"

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)

    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        return [ExtractedMemory(**item) for item in items]
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse extracted memories: %s — raw: %s", e, raw[:200])
        return []

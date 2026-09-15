/** API client for communicating with the FastAPI backend. */

import type {
  ChatResponse,
  ConflictDetectionResponse,
  Conversation,
  ConversationMessage,
  ConversationMemoryCandidate,
  ExtractResponse,
  Memory,
  MemoryExplainResponse,
  MemoryHistoryResponse,
  SearchResult,
  TokenResponse,
  User,
  UserMemoryPolicy,
  EvaluationDataset,
  EvaluationCase,
  EvaluationRun,
  EvaluationResult,
  MemoryQualityResult,
  WalletNonceResponse,
  WalletAuthResponse,
  Agent,
  AgentCreateRequest,
  AgentCreateResponse,
  AgentPermissionType,
  PermissionGrant,
  AgentAuditLog,
} from '@/types';

const BASE = ''; // proxied via next.config.js rewrites

function authHeaders(token: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------- Auth ----------

export async function register(
  email: string,
  password: string,
  displayName: string
): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return handleResponse<TokenResponse>(res);
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse<TokenResponse>(res);
}

export async function getMe(token: string): Promise<User> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: authHeaders(token),
  });
  return handleResponse<User>(res);
}

export async function getWalletNonce(
  address: string,
  chainId = 10143
): Promise<WalletNonceResponse> {
  const query = new URLSearchParams({
    address,
    chain_id: String(chainId),
  });
  const res = await fetch(`${BASE}/api/auth/wallet/nonce?${query.toString()}`);
  return handleResponse<WalletNonceResponse>(res);
}

export async function verifyWallet(
  payload: {
    address: string;
    signature: string;
    nonce: string;
  },
  token?: string | null
): Promise<WalletAuthResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}/api/auth/wallet/verify`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });
  return handleResponse<WalletAuthResponse>(res);
}

// ---------- Memories ----------

export async function listMemories(
  token: string,
  options?: {
    category?: string;
    memory_type?: string;
    source?: string;
    status?: string;
    offset?: number;
    limit?: number;
  } | string
): Promise<Memory[]> {
  const query = new URLSearchParams();
  if (typeof options === 'string') {
    if (options) query.set('category', options);
  } else if (options) {
    if (options.category) query.set('category', options.category);
    if (options.memory_type) query.set('memory_type', options.memory_type);
    if (options.source) query.set('source', options.source);
    if (options.status) query.set('status', options.status);
    if (options.offset !== undefined) query.set('offset', String(options.offset));
    if (options.limit !== undefined) query.set('limit', String(options.limit));
  }
  const qs = query.toString();
  const res = await fetch(`${BASE}/api/memories${qs ? `?${qs}` : ''}`, {
    headers: authHeaders(token),
  });
  return handleResponse<Memory[]>(res);
}

export async function getMemoryPolicy(token: string): Promise<UserMemoryPolicy> {
  const res = await fetch(`${BASE}/api/memories/policy`, {
    headers: authHeaders(token),
  });
  return handleResponse<UserMemoryPolicy>(res);
}

export async function updateMemoryPolicy(
  token: string,
  data: Partial<{
    memory_enabled: boolean;
    require_confirmation: boolean;
    allow_memory_retrieval: boolean;
    allow_ai_extraction: boolean;
  }>
): Promise<UserMemoryPolicy> {
  const res = await fetch(`${BASE}/api/memories/policy`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse<UserMemoryPolicy>(res);
}

export async function explainMemory(
  token: string,
  id: string
): Promise<MemoryExplainResponse> {
  const res = await fetch(`${BASE}/api/memories/${id}/explain`, {
    headers: authHeaders(token),
  });
  return handleResponse<MemoryExplainResponse>(res);
}

export async function getMemoryHistory(
  token: string,
  id: string
): Promise<MemoryHistoryResponse> {
  const res = await fetch(`${BASE}/api/memories/${id}/history`, {
    headers: authHeaders(token),
  });
  return handleResponse<MemoryHistoryResponse>(res);
}

export async function createMemory(
  token: string,
  data: {
    category: string;
    key: string;
    content: string;
    confidence?: number;
    is_shared?: boolean;
    tags?: string;
  }
): Promise<Memory> {
  const res = await fetch(`${BASE}/api/memories`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse<Memory>(res);
}

export async function updateMemory(
  token: string,
  id: string,
  data: Partial<{
    category: string;
    key: string;
    content: string;
    confidence: number;
    is_shared: boolean;
    tags: string;
  }>
): Promise<Memory> {
  const res = await fetch(`${BASE}/api/memories/${id}`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse<Memory>(res);
}

export async function deleteMemory(
  token: string,
  id: string
): Promise<void> {
  const res = await fetch(`${BASE}/api/memories/${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
}

export async function archiveMemory(token: string, id: string): Promise<Memory> {
  const res = await fetch(`${BASE}/api/memories/${id}/archive`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse<Memory>(res);
}

export async function restoreMemory(token: string, id: string): Promise<Memory> {
  const res = await fetch(`${BASE}/api/memories/${id}/restore`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse<Memory>(res);
}

export async function detectConflicts(
  token: string,
  data: { key?: string; content: string; memory_type?: string }
): Promise<ConflictDetectionResponse> {
  const res = await fetch(`${BASE}/api/memories/detect-conflicts`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse<ConflictDetectionResponse>(res);
}

export async function exportMemories(token: string): Promise<{
  memories: Memory[];
  exported_at: string;
  passport_id: string;
}> {
  const res = await fetch(`${BASE}/api/memories/export/all`, {
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function importMemories(
  token: string,
  items: { category: string; key: string; content: string; confidence?: number; tags?: string }[]
): Promise<Memory[]> {
  const res = await fetch(`${BASE}/api/memories/import/batch`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(items),
  });
  return handleResponse<Memory[]>(res);
}

// ---------- Search ----------

export async function searchMemories(
  token: string,
  query: string,
  topK = 5,
  category?: string
): Promise<SearchResult[]> {
  const res = await fetch(`${BASE}/api/search`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ query, top_k: topK, category }),
  });
  return handleResponse<SearchResult[]>(res);
}

// ---------- Chat ----------

export async function chat(
  token: string,
  message: string,
  conversationIdOrHistory?: string | null | { role: string; content: string }[],
  history?: { role: string; content: string }[] | string,
  agentRole = 'general'
): Promise<ChatResponse> {
  let convId: string | undefined = undefined;
  let hist: { role: string; content: string }[] = [];
  let role = agentRole;

  if (typeof conversationIdOrHistory === 'string') {
    convId = conversationIdOrHistory || undefined;
    hist = Array.isArray(history) ? history : [];
    if (typeof history === 'string') {
      role = history;
    }
  } else if (Array.isArray(conversationIdOrHistory)) {
    hist = conversationIdOrHistory;
    if (typeof history === 'string') {
      role = history;
    }
  }

  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      message,
      conversation_id: convId,
      history: hist,
      agent_role: role,
    }),
  });
  return handleResponse<ChatResponse>(res);
}

// ---------- Conversations & Candidates (Phase 3.0C & 3.0D) ----------

export async function createConversation(token: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/api/conversations`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse<Conversation>(res);
}

export async function listConversations(
  token: string,
  limit = 50
): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/api/conversations?limit=${limit}`, {
    headers: authHeaders(token),
  });
  return handleResponse<Conversation[]>(res);
}

export async function getConversation(
  token: string,
  conversationId: string
): Promise<Conversation> {
  const res = await fetch(`${BASE}/api/conversations/${conversationId}`, {
    headers: authHeaders(token),
  });
  return handleResponse<Conversation>(res);
}

export async function getConversationMessages(
  token: string,
  conversationId: string,
  limit = 50
): Promise<ConversationMessage[]> {
  const res = await fetch(
    `${BASE}/api/conversations/${conversationId}/messages?limit=${limit}`,
    {
      headers: authHeaders(token),
    }
  );
  return handleResponse<ConversationMessage[]>(res);
}

export async function deleteConversation(
  token: string,
  conversationId: string
): Promise<void> {
  const res = await fetch(`${BASE}/api/conversations/${conversationId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
}

export async function extractMemoryFromConversation(
  token: string,
  conversationId: string,
  messageIds?: string[]
): Promise<{ conversation_id: string; candidates: ConversationMemoryCandidate[] }> {
  const res = await fetch(
    `${BASE}/api/conversations/${conversationId}/extract-memory`,
    {
      method: 'POST',
      headers: authHeaders(token),
      body: JSON.stringify(messageIds ? { message_ids: messageIds } : {}),
    }
  );
  return handleResponse<{ conversation_id: string; candidates: ConversationMemoryCandidate[] }>(res);
}

export async function confirmMemoryFromConversation(
  token: string,
  conversationId: string,
  candidate: ConversationMemoryCandidate,
  userEdits?: { content?: string; key?: string; tags?: string }
): Promise<Memory> {
  const res = await fetch(
    `${BASE}/api/conversations/${conversationId}/confirm-memory`,
    {
      method: 'POST',
      headers: authHeaders(token),
      body: JSON.stringify({
        candidate,
        user_edits: userEdits || undefined,
      }),
    }
  );
  return handleResponse<Memory>(res);
}

export async function saveExtracted(
  token: string,
  items: {
    category: string;
    key: string;
    content: string;
    source?: string;
    confidence?: number;
  }[]
): Promise<Memory[]> {
  const res = await fetch(`${BASE}/api/chat/save-extracted`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(items),
  });
  return handleResponse<Memory[]>(res);
}

export async function extractMemories(
  token: string,
  text: string
): Promise<ExtractResponse> {
  const res = await fetch(`${BASE}/api/memories/extract`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ text }),
  });
  return handleResponse<ExtractResponse>(res);
}

export async function supersedeMemory(
  token: string,
  memoryId: string,
  replacementMemoryId: string,
  validUntil?: string
): Promise<Memory> {
  const res = await fetch(`${BASE}/api/memories/${memoryId}/supersede`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      replacement_memory_id: replacementMemoryId,
      valid_until: validUntil || undefined,
    }),
  });
  return handleResponse<Memory>(res);
}

// ---------- Evaluation API (Phase 5.6E) ----------

export async function listEvaluationDatasets(
  token: string,
  offset = 0,
  limit = 50
): Promise<EvaluationDataset[]> {
  const res = await fetch(`${BASE}/api/evaluation/datasets?offset=${offset}&limit=${limit}`, {
    headers: authHeaders(token),
  });
  return handleResponse<EvaluationDataset[]>(res);
}

export async function getEvaluationDataset(
  token: string,
  id: string
): Promise<EvaluationDataset> {
  const res = await fetch(`${BASE}/api/evaluation/datasets/${id}`, {
    headers: authHeaders(token),
  });
  return handleResponse<EvaluationDataset>(res);
}

export async function createEvaluationDataset(
  token: string,
  data: { name: string; description?: string; is_system?: boolean }
): Promise<EvaluationDataset> {
  const res = await fetch(`${BASE}/api/evaluation/datasets`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      name: data.name,
      description: data.description || '',
      is_system: data.is_system || false,
    }),
  });
  return handleResponse<EvaluationDataset>(res);
}

export async function listEvaluationCases(
  token: string,
  datasetId: string,
  offset = 0,
  limit = 50
): Promise<EvaluationCase[]> {
  const res = await fetch(
    `${BASE}/api/evaluation/datasets/${datasetId}/cases?offset=${offset}&limit=${limit}`,
    {
      headers: authHeaders(token),
    }
  );
  return handleResponse<EvaluationCase[]>(res);
}

export async function createEvaluationCase(
  token: string,
  datasetId: string,
  data: {
    query: string;
    expected_memory_ids?: string[];
    expected_relevance?: Record<string, number>;
    tags?: string;
    temporal_anchor?: string | null;
  }
): Promise<EvaluationCase> {
  const res = await fetch(`${BASE}/api/evaluation/datasets/${datasetId}/cases`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      query: data.query,
      expected_memory_ids: data.expected_memory_ids || [],
      expected_relevance: data.expected_relevance || {},
      tags: data.tags || '',
      temporal_anchor: data.temporal_anchor || null,
    }),
  });
  return handleResponse<EvaluationCase>(res);
}

export async function listEvaluationRuns(
  token: string,
  datasetId: string,
  offset = 0,
  limit = 50
): Promise<EvaluationRun[]> {
  const res = await fetch(
    `${BASE}/api/evaluation/datasets/${datasetId}/runs?offset=${offset}&limit=${limit}`,
    {
      headers: authHeaders(token),
    }
  );
  return handleResponse<EvaluationRun[]>(res);
}

export async function getEvaluationRun(
  token: string,
  runId: string
): Promise<EvaluationRun> {
  const res = await fetch(`${BASE}/api/evaluation/runs/${runId}`, {
    headers: authHeaders(token),
  });
  return handleResponse<EvaluationRun>(res);
}

export async function createEvaluationRun(
  token: string,
  datasetId: string,
  data: {
    name: string;
    app_version?: string;
    retrieval_config?: Record<string, any>;
  }
): Promise<EvaluationRun> {
  const res = await fetch(`${BASE}/api/evaluation/datasets/${datasetId}/runs`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      name: data.name,
      app_version: data.app_version || '1.9.0',
      retrieval_config: data.retrieval_config || {},
    }),
  });
  return handleResponse<EvaluationRun>(res);
}

export async function executeEvaluationRun(
  token: string,
  runId: string
): Promise<EvaluationRun> {
  const res = await fetch(`${BASE}/api/evaluation/runs/${runId}/execute`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse<EvaluationRun>(res);
}

export async function getEvaluationRunMetrics(
  token: string,
  runId: string
): Promise<Record<string, any>> {
  const res = await fetch(`${BASE}/api/evaluation/runs/${runId}/metrics`, {
    headers: authHeaders(token),
  });
  return handleResponse<Record<string, any>>(res);
}

export async function listEvaluationRunResults(
  token: string,
  runId: string,
  offset = 0,
  limit = 50
): Promise<EvaluationResult[]> {
  const res = await fetch(
    `${BASE}/api/evaluation/runs/${runId}/results?offset=${offset}&limit=${limit}`,
    {
      headers: authHeaders(token),
    }
  );
  return handleResponse<EvaluationResult[]>(res);
}

export async function getMemoryQuality(
  token: string,
  memoryId: string
): Promise<MemoryQualityResult> {
  const res = await fetch(`${BASE}/api/evaluation/memories/${memoryId}/quality`, {
    headers: authHeaders(token),
  });
  return handleResponse<MemoryQualityResult>(res);
}

// ---------- Agent Access Control (Phase 6.5) ----------

export async function listAgents(token: string): Promise<Agent[]> {
  const res = await fetch(`${BASE}/api/agents`, {
    headers: authHeaders(token),
  });
  return handleResponse<Agent[]>(res);
}

export async function createAgent(
  token: string,
  data: AgentCreateRequest
): Promise<AgentCreateResponse> {
  const res = await fetch(`${BASE}/api/agents`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(data),
  });
  return handleResponse<AgentCreateResponse>(res);
}

export async function getAgent(token: string, agentId: string): Promise<Agent> {
  const res = await fetch(`${BASE}/api/agents/${agentId}`, {
    headers: authHeaders(token),
  });
  return handleResponse<Agent>(res);
}

export async function revokeAgent(token: string, agentId: string): Promise<Agent> {
  const res = await fetch(`${BASE}/api/agents/${agentId}/revoke`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  return handleResponse<Agent>(res);
}

export async function listAgentPermissions(
  token: string,
  agentId: string
): Promise<PermissionGrant[]> {
  const res = await fetch(`${BASE}/api/agents/${agentId}/permissions`, {
    headers: authHeaders(token),
  });
  return handleResponse<PermissionGrant[]>(res);
}

export async function grantAgentPermission(
  token: string,
  agentId: string,
  permission: AgentPermissionType,
  expiresAt?: string | null
): Promise<PermissionGrant> {
  const res = await fetch(`${BASE}/api/agents/${agentId}/permissions`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ permission, expires_at: expiresAt || null }),
  });
  return handleResponse<PermissionGrant>(res);
}

export async function revokeAgentPermission(
  token: string,
  agentId: string,
  permission: AgentPermissionType
): Promise<PermissionGrant> {
  const res = await fetch(
    `${BASE}/api/agents/${agentId}/permissions/${permission}/revoke`,
    {
      method: 'POST',
      headers: authHeaders(token),
    }
  );
  return handleResponse<PermissionGrant>(res);
}

export async function listAgentAuditLogs(
  token: string,
  offset = 0,
  limit = 50
): Promise<AgentAuditLog[]> {
  const res = await fetch(`${BASE}/api/agents/audit-logs?offset=${offset}&limit=${limit}`, {
    headers: authHeaders(token),
  });
  return handleResponse<AgentAuditLog[]>(res);
}

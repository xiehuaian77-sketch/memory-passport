/** API client for communicating with the FastAPI backend. */

import type {
  ChatResponse,
  ExtractResponse,
  Memory,
  SearchResult,
  TokenResponse,
  User,
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

// ---------- Memories ----------

export async function listMemories(
  token: string,
  category?: string
): Promise<Memory[]> {
  const params = category ? `?category=${category}` : '';
  const res = await fetch(`${BASE}/api/memories${params}`, {
    headers: authHeaders(token),
  });
  return handleResponse<Memory[]>(res);
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
  history: { role: string; content: string }[] = [],
  agentRole = 'general'
): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({
      message,
      history,
      agent_role: agentRole,
    }),
  });
  return handleResponse<ChatResponse>(res);
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

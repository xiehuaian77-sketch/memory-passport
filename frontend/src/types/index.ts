/** TypeScript types shared across the frontend. */

export interface User {
  id: string;
  email: string;
  passport_id: string;
  display_name: string;
  wallet_address: string | null;
  wallet_bound_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Memory {
  id: string;
  user_id: string;
  category: 'preference' | 'identity' | 'task' | 'context';
  key: string;
  content: string;
  source: 'manual' | 'ai_extracted' | 'imported';
  confidence: number;
  is_shared: boolean;
  tags: string;
  status?: 'active' | 'archived' | 'conflicted';
  version?: number;
  source_conversation_id?: string | null;
  source_message_id?: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface SearchResult {
  memory: Memory;
  score: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  reply: string;
  extracted_memories: ExtractedMemory[];
  loaded_memories: Memory[];
}

export interface ExtractedMemory {
  category: string;
  key: string;
  content: string;
  confidence: number;
}

export interface ExtractedCandidate {
  category: MemoryCategory;
  key: string;
  content: string;
  confidence: number;
  importance: number;
  tags: string;
  is_shared: boolean;
}

export interface ExtractResponse {
  raw_content: string;
  candidates: ExtractedCandidate[];
}

export interface MCPPassportResponse {
  passport_id: string;
  display_name: string;
  memories: Memory[];
}

export type MemoryCategory = 'preference' | 'identity' | 'task' | 'context';

export const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  preference: '偏好',
  identity: '身份',
  task: '任务',
  context: '上下文',
};

export const CATEGORY_COLORS: Record<MemoryCategory, string> = {
  preference: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  identity: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  task: 'bg-green-500/20 text-green-300 border-green-500/30',
  context: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
};

// ---------- Governance & Audit (Phase 3.2) ----------

export interface MemoryAuditLog {
  id: string;
  memory_id: string | null;
  user_id: string;
  actor_type: 'user' | 'ai' | 'system';
  actor_id: string;
  action: string;
  from_version: number | null;
  to_version: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface UserMemoryPolicy {
  user_id: string;
  memory_enabled: boolean;
  require_confirmation: boolean;
  allow_memory_retrieval: boolean;
  allow_ai_extraction: boolean;
  created_at: string;
  updated_at: string;
}

export interface MemoryExplainResponse {
  memory_id: string;
  key: string;
  memory_type: string;
  content: string;
  status: string;
  version: number;
  source: string;
  source_conversation_id: string | null;
  source_message_id: string | null;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  has_conflicts: boolean;
  conflict_count: number;
  audit_summary: Record<string, unknown>;
}

export interface MemoryHistoryResponse {
  memory_id: string;
  total_events: number;
  history: MemoryAuditLog[];
}

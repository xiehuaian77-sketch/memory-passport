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
  status?: 'active' | 'archived' | 'conflicted' | 'superseded';
  version?: number;
  source_conversation_id?: string | null;
  source_message_id?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  superseded_by_memory_id?: string | null;
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

export interface LoadedMemoryItem {
  id: string;
  memory_type: string;
  content: string;
  similarity?: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  loaded_memories?: LoadedMemoryItem[];
}

export interface ChatResponse {
  reply: string;
  response?: string;
  conversation_id?: string | null;
  extracted_memories: ExtractedMemory[];
  loaded_memories: LoadedMemoryItem[];
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

// ---------- Conversations & Candidates (Phase 3.0C & 3.0D) ----------

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: ConversationMessage[];
}

export interface ConversationMemoryCandidate {
  id: string;
  memory_type: 'preference' | 'identity' | 'task' | 'context';
  key: string;
  content: string;
  importance: number;
  confidence: number;
  tags: string[] | string;
  reason: string;
  source: string;
  raw_content: string;
  signature: string;
}

export interface ConflictItem {
  conflict_type: 'key_conflict' | 'semantic_conflict' | 'contradiction';
  existing_memory_id: string;
  existing_key: string;
  existing_content: string;
  similarity?: number | null;
  message?: string;
  recommendation?: string;
  classification?: 'DUPLICATE' | 'SIMILAR' | 'RELATED' | 'UPDATE' | 'SUPERSEDE' | 'CONTRADICTION' | 'UNRELATED';
  conflict_score?: number;
  confidence?: number;
  user_reason?: string;
  tier_applied?: string;
}

export interface ConflictDetectionResponse {
  has_conflict: boolean;
  conflicts: ConflictItem[];
}

// ---------- Evaluation Types (Phase 5.6E) ----------

export interface EvaluationDataset {
  id: string;
  user_id: string;
  name: string;
  description: string;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvaluationCase {
  id: string;
  dataset_id: string;
  user_id: string;
  query: string;
  expected_memory_ids: string[];
  expected_relevance: Record<string, number>;
  tags: string;
  temporal_anchor: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvaluationRun {
  id: string;
  dataset_id: string;
  user_id: string;
  name: string;
  app_version: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  retrieval_config: Record<string, any>;
  summary_metrics: Record<string, any> | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationResult {
  id: string;
  run_id: string;
  case_id: string;
  user_id: string;
  retrieved_memory_ids: string[];
  scores: number[];
  metrics: Record<string, any>;
  latency_ms: number;
  context_chars: number;
  passed: boolean;
  details: Record<string, any> | null;
  created_at: string;
}

export interface QualityDimensionScore {
  name: string;
  score: number;
  weight: number;
  reason: string;
  raw_risk: number | null;
}

export interface MemoryQualityResult {
  memory_id: string;
  user_id: string;
  overall_score: number;
  dimensions: Record<string, QualityDimensionScore>;
  warnings: string[];
  evaluated_at: string;
  summary_reason: string;
}

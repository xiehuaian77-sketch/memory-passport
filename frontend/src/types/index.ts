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

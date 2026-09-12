'use client';

import { useEffect, useState, useCallback, Suspense } from 'react';
import {
  Plus,
  Search,
  Download,
  Upload,
  Filter,
  Inbox,
  Archive,
  AlertTriangle,
  Layers,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { useRouter, useSearchParams } from 'next/navigation';
import MemoryCard from '@/components/memory-card';
import MemoryEditor from '@/components/memory-editor';
import MemoryExplainModal from '@/components/memory-explain-modal';
import MemoryInbox from '@/components/memory-inbox';
import type {
  Memory,
  MemoryCategory,
  ConversationMemoryCandidate,
} from '@/types';
import * as api from '@/lib/api';

const CATEGORIES: { value: MemoryCategory | ''; label: string }[] = [
  { value: '', label: '全部类别' },
  { value: 'preference', label: '偏好' },
  { value: 'identity', label: '身份' },
  { value: 'task', label: '任务' },
  { value: 'context', label: '上下文' },
];

type StatusTab = 'active' | 'inbox' | 'archived' | 'conflicted' | 'all';

const PAGE_SIZE = 12;

function MemoryCenterContent() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // Navigation tabs
  const [activeTab, setActiveTab] = useState<StatusTab>('active');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [candidates, setCandidates] = useState<ConversationMemoryCandidate[]>([]);
  const [filter, setFilter] = useState<MemoryCategory | ''>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Memory[] | null>(null);

  // Pagination
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  // Modals
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [explainMemoryId, setExplainMemoryId] = useState<string | null>(null);
  const [explainTab, setExplainTab] = useState<'explain' | 'history'>('explain');

  // Loading & Feedback
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const showFeedback = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(''), 3500);
  };

  // Check URL query parameters for default tab
  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'inbox') {
      setActiveTab('inbox');
    }
  }, [searchParams]);

  // Load stored candidates from localStorage (e.g. sent from Chat page)
  useEffect(() => {
    try {
      const stored = localStorage.getItem('mp_pending_candidates');
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          setCandidates(parsed);
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const syncCandidates = (newCandidates: ConversationMemoryCandidate[]) => {
    setCandidates(newCandidates);
    try {
      localStorage.setItem('mp_pending_candidates', JSON.stringify(newCandidates));
    } catch {
      // ignore
    }
  };

  const fetchMemories = useCallback(async () => {
    if (!token || activeTab === 'inbox') return;
    try {
      setLoading(true);
      setError('');
      const statusParam =
        activeTab === 'all'
          ? 'all'
          : activeTab === 'archived'
          ? 'archived'
          : activeTab === 'conflicted'
          ? 'conflicted'
          : 'active';

      const offset = (page - 1) * PAGE_SIZE;
      const data = await api.listMemories(token, {
        category: filter || undefined,
        status: statusParam,
        offset,
        limit: PAGE_SIZE + 1,
      });

      if (data.length > PAGE_SIZE) {
        setHasMore(true);
        setMemories(data.slice(0, PAGE_SIZE));
      } else {
        setHasMore(false);
        setMemories(data);
      }
      setSearchResults(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载记忆失败');
    } finally {
      setLoading(false);
    }
  }, [token, activeTab, filter, page]);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
      return;
    }
    if (token) fetchMemories();
  }, [isLoading, user, token, fetchMemories, router]);

  const handleSearch = async () => {
    if (!token || !searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      setLoading(true);
      const results = await api.searchMemories(token, searchQuery, 20);
      setSearchResults(results.map((r) => r.memory));
    } catch (err) {
      setError(err instanceof Error ? err.message : '搜索失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (data: {
    category: string;
    key: string;
    content: string;
    confidence: number;
    is_shared: boolean;
    tags: string;
  }) => {
    if (!token) return;
    try {
      if (editingMemory) {
        await api.updateMemory(token, editingMemory.id, data);
        showFeedback('记忆已更新 (已创建新审计版本)');
      } else {
        await api.createMemory(token, data);
        showFeedback('新记忆已创建');
      }
      setEditorOpen(false);
      setEditingMemory(null);
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  };

  const handleArchive = async (id: string) => {
    if (!token) return;
    try {
      await api.archiveMemory(token, id);
      showFeedback('记忆已归档 (退出检索上下文)');
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '归档失败');
    }
  };

  const handleRestore = async (id: string) => {
    if (!token) return;
    try {
      await api.restoreMemory(token, id);
      showFeedback('记忆已恢复至活跃状态');
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '恢复失败');
    }
  };

  const handleDelete = async (id: string) => {
    if (!token || !confirm('确定永久删除这条记忆？此操作将记录入审计日志且不可恢复。')) return;
    try {
      await api.deleteMemory(token, id);
      showFeedback('记忆已删除 (审计日志已留存)');
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  const handleToggleShare = async (m: Memory) => {
    if (!token) return;
    try {
      await api.updateMemory(token, m.id, { is_shared: !m.is_shared });
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新共享状态失败');
    }
  };

  // Candidate Confirm (Save)
  const handleConfirmCandidate = async (cand: ConversationMemoryCandidate) => {
    if (!token) return;
    try {
      // Find source conversation id or fallback to candidate's
      const convId = (cand as any).source_conversation_id || (cand as any).conversation_id || 'default_conv';
      await api.confirmMemoryFromConversation(token, convId, cand);
      const remaining = candidates.filter((c) => c.id !== cand.id);
      syncCandidates(remaining);
      showFeedback(`已成功入库记忆: ${cand.key}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认入库失败');
    }
  };

  // Candidate Edit and Confirm (Single Atomic DB Transaction)
  const handleEditAndConfirmCandidate = async (
    cand: ConversationMemoryCandidate,
    editedContent: string,
    editedKey: string
  ) => {
    if (!token) return;
    try {
      const convId = (cand as any).source_conversation_id || (cand as any).conversation_id || 'default_conv';
      // Atomic: validates original HMAC and persists user edits within the same DB transaction
      await api.confirmMemoryFromConversation(token, convId, cand, {
        content: editedContent,
        key: editedKey,
      });
      const remaining = candidates.filter((c) => c.id !== cand.id);
      syncCandidates(remaining);
      showFeedback(`已保存修改并入库 (原子事务): ${editedKey}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存修改失败');
    }
  };

  // Candidate Dismiss
  const handleDismissCandidate = (candId: string) => {
    const remaining = candidates.filter((c) => c.id !== candId);
    syncCandidates(remaining);
    showFeedback('已忽略该提炼候选');
  };

  const handleExport = async () => {
    if (!token) return;
    try {
      const data = await api.exportMemories(token);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `memory-passport-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败');
    }
  };

  const handleImport = async () => {
    if (!token) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const data = JSON.parse(text);
        const items = (data.memories || data).map((m: Memory) => ({
          category: m.category,
          key: m.key,
          content: m.content,
          confidence: m.confidence || 0.8,
          tags: m.tags || '',
        }));
        await api.importMemories(token, items);
        showFeedback('记忆导入成功');
        await fetchMemories();
      } catch (err) {
        setError(err instanceof Error ? err.message : '导入失败');
      }
    };
    input.click();
  };

  const displayMemories = searchResults ?? memories;

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      {/* Top Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <Layers className="h-6 w-6 text-blue-400" />
            记忆中心 (Memory Center)
          </h1>
          <p className="text-sm text-slate-400">
            可控制 · 可解释 · 经授权的长期个人记忆网络 · Passport: {user?.passport_id}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <Download className="h-4 w-4" /> 导出
          </button>
          <button
            onClick={handleImport}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <Upload className="h-4 w-4" /> 导入
          </button>
          <button
            onClick={() => {
              setEditingMemory(null);
              setEditorOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-blue-600/20 hover:bg-blue-500 transition-all"
          >
            <Plus className="h-4 w-4" /> 手动添加
          </button>
        </div>
      </div>

      {/* Status Tabs Navigation */}
      <div className="mb-6 flex flex-wrap gap-2 border-b border-slate-800 pb-3">
        <button
          onClick={() => {
            setActiveTab('active');
            setPage(1);
          }}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'active'
              ? 'bg-blue-600 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          活跃记忆 (Active)
        </button>

        <button
          onClick={() => {
            setActiveTab('inbox');
            setPage(1);
          }}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'inbox'
              ? 'bg-cyan-600 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <Inbox className="h-4 w-4" />
          收件箱 (Inbox)
          {candidates.length > 0 && (
            <span className="rounded-full bg-cyan-400/20 px-1.5 py-0.2 text-xs font-bold text-cyan-300">
              {candidates.length}
            </span>
          )}
        </button>

        <button
          onClick={() => {
            setActiveTab('archived');
            setPage(1);
          }}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'archived'
              ? 'bg-slate-700 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <Archive className="h-4 w-4" />
          已归档 (Archived)
        </button>

        <button
          onClick={() => {
            setActiveTab('conflicted');
            setPage(1);
          }}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'conflicted'
              ? 'bg-amber-600 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          <AlertTriangle className="h-4 w-4" />
          冲突预警 (Conflicted)
        </button>

        <button
          onClick={() => {
            setActiveTab('all');
            setPage(1);
          }}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'all'
              ? 'bg-slate-700 text-white shadow'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          }`}
        >
          全部 (All)
        </button>
      </div>

      {/* Notifications / Alerts */}
      {feedback && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-300 animate-fade-in">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          {feedback}
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-red-500/30 bg-red-900/20 px-4 py-3 text-sm text-red-400 animate-fade-in">
          <span>{error}</span>
          <button onClick={() => setError('')} className="underline text-xs">
            关闭
          </button>
        </div>
      )}

      {/* Active Tab View: Memory Inbox */}
      {activeTab === 'inbox' ? (
        <MemoryInbox
          candidates={candidates}
          token={token || ''}
          onConfirm={handleConfirmCandidate}
          onEditAndConfirm={handleEditAndConfirmCandidate}
          onDismiss={handleDismissCandidate}
        />
      ) : (
        /* Regular Memory Center View (Active / Archived / Conflicted / All) */
        <>
          {/* Search + Filter Bar */}
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="语义 / 关键词搜索记忆..."
                className="w-full rounded-xl border border-slate-700 bg-slate-800/80 pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <button
              onClick={handleSearch}
              className="rounded-xl bg-slate-800 border border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-700 transition-colors"
            >
              搜索
            </button>

            <div className="flex items-center gap-1">
              <Filter className="h-4 w-4 text-slate-500" />
              {CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  onClick={() => {
                    setFilter(c.value as MemoryCategory | '');
                    setPage(1);
                  }}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    filter === c.value
                      ? 'bg-blue-600 text-white shadow'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* Search Results Notice */}
          {searchResults && (
            <div className="mb-4 flex items-center justify-between rounded-xl bg-blue-950/20 border border-blue-500/20 px-4 py-2.5 text-xs text-blue-300">
              <span>共检索到 {searchResults.length} 条高相关度记忆</span>
              <button
                onClick={() => {
                  setSearchResults(null);
                  setSearchQuery('');
                }}
                className="underline hover:text-white"
              >
                清除搜索结果
              </button>
            </div>
          )}

          {/* Grid of Memory Cards */}
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
              <p className="mt-3 text-xs text-slate-500">加载记忆中...</p>
            </div>
          ) : displayMemories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/20">
              <p className="text-base font-semibold text-slate-400 mb-1">
                {activeTab === 'archived'
                  ? '暂无已归档记忆'
                  : activeTab === 'conflicted'
                  ? '无潜在冲突记忆'
                  : '还没有匹配的记忆记录'}
              </p>
              <p className="text-xs text-slate-500 max-w-sm">
                {activeTab === 'archived'
                  ? '将长期不用的记忆归档后，AI 在生成回答时将不再加载它。'
                  : '在 AI 对话中提炼或点击「手动添加」，构建你的专属 Memory Passport。'}
              </p>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {displayMemories.map((m) => (
                <MemoryCard
                  key={m.id}
                  memory={m}
                  onEdit={(mem) => {
                    setEditingMemory(mem);
                    setEditorOpen(true);
                  }}
                  onDelete={handleDelete}
                  onArchive={handleArchive}
                  onRestore={handleRestore}
                  onExplain={(mem) => {
                    setExplainMemoryId(mem.id);
                    setExplainTab('explain');
                  }}
                  onHistory={(mem) => {
                    setExplainMemoryId(mem.id);
                    setExplainTab('history');
                  }}
                  onToggleShare={handleToggleShare}
                />
              ))}
            </div>
          )}

          {/* Pagination Controls */}
          {!searchResults && (memories.length > 0 || page > 1) && (
            <div className="mt-8 flex items-center justify-center gap-3 border-t border-slate-800/80 pt-6">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition-colors"
              >
                <ChevronLeft className="h-3.5 w-3.5" /> 上一页
              </button>
              <span className="text-xs text-slate-500">第 {page} 页</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore || loading}
                className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 disabled:opacity-40 transition-colors"
              >
                下一页 <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Explain & History Modal */}
      {explainMemoryId && token && (
        <MemoryExplainModal
          memoryId={explainMemoryId}
          token={token}
          initialTab={explainTab}
          onClose={() => setExplainMemoryId(null)}
        />
      )}

      {/* Editor Modal */}
      {editorOpen && (
        <MemoryEditor
          memory={editingMemory}
          onSave={handleSave}
          onClose={() => {
            setEditorOpen(false);
            setEditingMemory(null);
          }}
        />
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[60vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
        </div>
      }
    >
      <MemoryCenterContent />
    </Suspense>
  );
}

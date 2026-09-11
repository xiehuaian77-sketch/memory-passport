'use client';

import { useEffect, useState, useCallback } from 'react';
import { Plus, Search, Download, Upload, Filter } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import MemoryCard from '@/components/memory-card';
import MemoryEditor from '@/components/memory-editor';
import type { Memory, MemoryCategory } from '@/types';
import * as api from '@/lib/api';

const CATEGORIES: { value: MemoryCategory | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'preference', label: '偏好' },
  { value: 'identity', label: '身份' },
  { value: 'task', label: '任务' },
  { value: 'context', label: '上下文' },
];

export default function DashboardPage() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [filter, setFilter] = useState<MemoryCategory | ''>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Memory[] | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchMemories = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      const data = await api.listMemories(token, filter || undefined);
      setMemories(data);
      setSearchResults(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, [token, filter]);

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
      const results = await api.searchMemories(token, searchQuery, 10);
      setSearchResults(results.map((r) => r.memory));
    } catch (err) {
      setError(err instanceof Error ? err.message : '搜索失败');
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
      } else {
        await api.createMemory(token, data);
      }
      setEditorOpen(false);
      setEditingMemory(null);
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  };

  const handleDelete = async (id: string) => {
    if (!token || !confirm('确定删除这条记忆？')) return;
    try {
      await api.deleteMemory(token, id);
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
      setError(err instanceof Error ? err.message : '更新失败');
    }
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
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">记忆面板</h1>
          <p className="text-sm text-slate-400">
            共 {memories.length} 条记忆 · Passport: {user?.passport_id}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            <Download className="h-4 w-4" /> 导出
          </button>
          <button
            onClick={handleImport}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            <Upload className="h-4 w-4" /> 导入
          </button>
          <button
            onClick={() => {
              setEditingMemory(null);
              setEditorOpen(true);
            }}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            <Plus className="h-4 w-4" /> 添加记忆
          </button>
        </div>
      </div>

      {/* Search + Filter */}
      <div className="mb-6 flex flex-wrap gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="语义搜索记忆..."
            className="w-full rounded-lg border border-slate-700 bg-slate-800 pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <button
          onClick={handleSearch}
          className="rounded-lg bg-slate-700 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-600"
        >
          搜索
        </button>
        <div className="flex items-center gap-1">
          <Filter className="h-4 w-4 text-slate-500" />
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              onClick={() => setFilter(c.value as MemoryCategory | '')}
              className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                filter === c.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg bg-red-900/20 border border-red-500/30 px-4 py-3 text-sm text-red-400">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">关闭</button>
        </div>
      )}

      {/* Search results indicator */}
      {searchResults && (
        <div className="mb-4 flex items-center gap-2 text-sm text-slate-400">
          <span>搜索结果: {searchResults.length} 条</span>
          <button
            onClick={() => {
              setSearchResults(null);
              setSearchQuery('');
            }}
            className="text-blue-400 underline"
          >
            清除搜索
          </button>
        </div>
      )}

      {/* Memory grid */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
        </div>
      ) : displayMemories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-500">
          <p className="text-lg mb-2">还没有记忆</p>
          <p className="text-sm">点击「添加记忆」开始构建你的 Memory Passport</p>
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
              onToggleShare={handleToggleShare}
            />
          ))}
        </div>
      )}

      {/* Editor modal */}
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

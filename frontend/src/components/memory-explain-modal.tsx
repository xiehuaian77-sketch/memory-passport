'use client';

import { useState, useEffect } from 'react';
import {
  X,
  ShieldCheck,
  History as HistoryIcon,
  Info,
  Clock,
  AlertTriangle,
  User,
  Bot,
  Cpu,
} from 'lucide-react';
import type { MemoryExplainResponse, MemoryHistoryResponse } from '@/types';
import * as api from '@/lib/api';
import { formatDate } from '@/lib/utils';

interface MemoryExplainModalProps {
  memoryId: string;
  token: string;
  initialTab?: 'explain' | 'history';
  onClose: () => void;
}

export default function MemoryExplainModal({
  memoryId,
  token,
  initialTab = 'explain',
  onClose,
}: MemoryExplainModalProps) {
  const [activeTab, setActiveTab] = useState<'explain' | 'history'>(initialTab);
  const [explainData, setExplainData] = useState<MemoryExplainResponse | null>(null);
  const [historyData, setHistoryData] = useState<MemoryHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      try {
        setLoading(true);
        setError('');
        const [exp, hist] = await Promise.all([
          api.explainMemory(token, memoryId),
          api.getMemoryHistory(token, memoryId),
        ]);
        if (isMounted) {
          setExplainData(exp);
          setHistoryData(hist);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : '加载可解释性信息失败');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [memoryId, token]);

  const getActorIcon = (actor: string) => {
    if (actor === 'ai') return <Bot className="h-4 w-4 text-cyan-400" />;
    if (actor === 'system') return <Cpu className="h-4 w-4 text-slate-400" />;
    return <User className="h-4 w-4 text-purple-400" />;
  };

  const getActionLabel = (action: string) => {
    switch (action) {
      case 'CREATE':
        return '创建记忆';
      case 'CONFIRM':
        return '用户确认候选入库';
      case 'UPDATE':
        return '更新记忆';
      case 'ARCHIVE':
        return '归档记忆';
      case 'RESTORE':
        return '恢复记忆';
      case 'DELETE':
        return '删除记忆';
      case 'EXTRACT_CANDIDATE':
        return '提取候选';
      case 'CONFLICT_DETECTED':
        return '检测到冲突';
      default:
        return action;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm animate-fade-in">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-800 p-4">
          <div className="flex items-center gap-2">
            <Info className="h-5 w-5 text-blue-400" />
            <h3 className="text-base font-semibold text-slate-100">
              记忆可解释性与治理画像
            </h3>
            {explainData && (
              <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400 font-mono">
                v{explainData.version}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 bg-slate-900/50 px-4">
          <button
            onClick={() => setActiveTab('explain')}
            className={`flex items-center gap-2 border-b-2 py-3 px-3 text-sm font-medium transition-colors ${
              activeTab === 'explain'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
            画像与溯源 (Explain)
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-2 border-b-2 py-3 px-3 text-sm font-medium transition-colors ${
              activeTab === 'history'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <HistoryIcon className="h-4 w-4" />
            审计历史 (History)
            {historyData && (
              <span className="rounded-full bg-slate-800 px-2 py-0.2 text-xs text-slate-400">
                {historyData.total_events}
              </span>
            )}
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
              <p className="mt-3 text-xs text-slate-500">正在分析记忆审计画像...</p>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-red-500/30 bg-red-900/20 p-4 text-sm text-red-400">
              {error}
            </div>
          ) : activeTab === 'explain' && explainData ? (
            <div className="space-y-4">
              {/* Content Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs uppercase font-medium text-slate-400">
                    记忆键名: <span className="text-slate-200 font-mono">{explainData.key}</span>
                  </span>
                  <span className="rounded bg-blue-500/20 px-2 py-0.5 text-xs text-blue-300">
                    {explainData.memory_type}
                  </span>
                </div>
                <p className="text-sm text-slate-200 whitespace-pre-wrap">
                  {explainData.content}
                </p>
              </div>

              {/* Status & Eligibility Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-slate-800 bg-slate-800/20 p-3">
                  <span className="text-xs text-slate-500 block mb-1">当前状态</span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        explainData.status === 'active'
                          ? 'bg-emerald-400'
                          : explainData.status === 'archived'
                          ? 'bg-slate-400'
                          : 'bg-amber-400'
                      }`}
                    />
                    <span className="text-sm font-medium text-slate-200 capitalize">
                      {explainData.status === 'active'
                        ? '活跃 (Active)'
                        : explainData.status === 'archived'
                        ? '已归档 (Archived)'
                        : '冲突中 (Conflicted)'}
                    </span>
                  </div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-800/20 p-3">
                  <span className="text-xs text-slate-500 block mb-1">AI 检索状态</span>
                  <span
                    className={`text-sm font-medium ${
                      explainData.is_active ? 'text-emerald-400' : 'text-slate-500'
                    }`}
                  >
                    {explainData.is_active ? '✓ 正在参与检索' : '✕ 未参与检索 (已归档)'}
                  </span>
                </div>
              </div>

              {/* Conflict Status */}
              {explainData.has_conflicts && (
                <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-sm text-amber-300">
                  <div className="flex items-center gap-2 font-semibold">
                    <AlertTriangle className="h-4 w-4 text-amber-400" />
                    存在潜在冲突警示
                  </div>
                  <p className="mt-1 text-xs text-amber-400/80">
                    该记忆可能与库内其他事实存在逻辑或键名重叠，可在冲突列表中核对。
                  </p>
                </div>
              )}

              {/* Provenance & Timeline */}
              <div className="rounded-xl border border-slate-800 bg-slate-800/30 p-4 space-y-2.5 text-xs text-slate-400">
                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                  <span>记忆来源</span>
                  <span className="text-slate-300 font-medium capitalize">
                    {explainData.source === 'conversation' || explainData.source === 'ai_extracted'
                      ? 'AI 对话提炼'
                      : explainData.source === 'manual'
                      ? '用户手动创建'
                      : '批量导入'}
                  </span>
                </div>
                {explainData.source_conversation_id && (
                  <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                    <span>关联对话出处</span>
                    <span className="font-mono text-blue-400">
                      {explainData.source_conversation_id}
                    </span>
                  </div>
                )}
                <div className="flex justify-between items-center py-1 border-b border-slate-800/60">
                  <span>初次创建时间</span>
                  <span className="text-slate-300">{formatDate(explainData.created_at)}</span>
                </div>
                <div className="flex justify-between items-center py-1">
                  <span>最近变更时间</span>
                  <span className="text-slate-300">{formatDate(explainData.updated_at)}</span>
                </div>
              </div>
            </div>
          ) : activeTab === 'history' && historyData ? (
            <div className="space-y-4">
              {historyData.history.length === 0 ? (
                <div className="text-center py-8 text-slate-500 text-sm">
                  暂无审计历史记录
                </div>
              ) : (
                <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
                  {historyData.history.map((log) => (
                    <div key={log.id} className="relative group">
                      {/* Timeline dot */}
                      <div className="absolute -left-6 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
                        {getActorIcon(log.actor_type)}
                      </div>

                      {/* Log Entry Content */}
                      <div className="rounded-xl border border-slate-800/80 bg-slate-800/30 p-3.5">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-medium text-sm text-slate-200">
                            {getActionLabel(log.action)}
                          </span>
                          <span className="flex items-center gap-1 text-[11px] text-slate-500">
                            <Clock className="h-3 w-3" />
                            {formatDate(log.created_at)}
                          </span>
                        </div>

                        <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                          <span>操作主体: <span className="text-slate-300 uppercase">{log.actor_type}</span></span>
                          {log.to_version && (
                            <span>版本: <span className="font-mono text-cyan-400">v{log.to_version}</span></span>
                          )}
                        </div>

                        {log.metadata && Object.keys(log.metadata).length > 0 && (
                          <div className="mt-2 rounded bg-slate-900/60 p-2 text-[11px] font-mono text-slate-400 overflow-x-auto">
                            {Object.entries(log.metadata).map(([k, v]) => (
                              <div key={k} className="flex gap-1.5">
                                <span className="text-slate-500">{k}:</span>
                                <span className="text-slate-300 truncate">
                                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

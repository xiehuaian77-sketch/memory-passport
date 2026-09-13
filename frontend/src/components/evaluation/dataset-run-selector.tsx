'use client';

import { useState } from 'react';
import {
  Database,
  Play,
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  Sliders,
  Layers,
} from 'lucide-react';
import type { EvaluationDataset, EvaluationRun } from '@/types';
import * as api from '@/lib/api';

interface Props {
  token: string;
  datasets: EvaluationDataset[];
  selectedDatasetId: string | null;
  onSelectDataset: (id: string) => void;
  onDatasetCreated: () => void;
  runs: EvaluationRun[];
  selectedRunId: string | null;
  onSelectRun: (id: string) => void;
  onRunCreated: () => void;
  onRunExecuted: () => void;
  onShowFeedback: (msg: string) => void;
}

export default function DatasetRunSelector({
  token,
  datasets,
  selectedDatasetId,
  onSelectDataset,
  onDatasetCreated,
  runs,
  selectedRunId,
  onSelectRun,
  onRunCreated,
  onRunExecuted,
  onShowFeedback,
}: Props) {
  // Modal states
  const [showCreateDataset, setShowCreateDataset] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('');
  const [newDatasetDesc, setNewDatasetDesc] = useState('');
  const [isCreatingDataset, setIsCreatingDataset] = useState(false);

  const [showCreateRun, setShowCreateRun] = useState(false);
  const [newRunName, setNewRunName] = useState('');
  const [newRunStrategy, setNewRunStrategy] = useState('hybrid');
  const [newRunTopK, setNewRunTopK] = useState(5);
  const [isCreatingRun, setIsCreatingRun] = useState(false);

  // Run execution state
  const [isExecuting, setIsExecuting] = useState(false);
  const [actionError, setActionError] = useState('');

  const selectedRun = runs.find((r) => r.id === selectedRunId);

  const handleCreateDataset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDatasetName.trim()) return;
    setIsCreatingDataset(true);
    setActionError('');
    try {
      await api.createEvaluationDataset(token, {
        name: newDatasetName.trim(),
        description: newDatasetDesc.trim(),
      });
      setNewDatasetName('');
      setNewDatasetDesc('');
      setShowCreateDataset(false);
      onShowFeedback('测试集创建成功');
      onDatasetCreated();
    } catch (err: any) {
      setActionError(err.message || '创建测试集失败');
    } finally {
      setIsCreatingDataset(false);
    }
  };

  const handleCreateRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDatasetId || !newRunName.trim()) return;
    setIsCreatingRun(true);
    setActionError('');
    try {
      await api.createEvaluationRun(token, selectedDatasetId, {
        name: newRunName.trim(),
        retrieval_config: {
          search_mode: newRunStrategy,
          top_k: newRunTopK,
        },
      });
      setNewRunName('');
      setShowCreateRun(false);
      onShowFeedback('评测任务创建成功');
      onRunCreated();
    } catch (err: any) {
      setActionError(err.message || '创建评测任务失败');
    } finally {
      setIsCreatingRun(false);
    }
  };

  const handleExecuteRun = async () => {
    if (!selectedRunId || isExecuting) return;
    setIsExecuting(true);
    setActionError('');
    try {
      await api.executeEvaluationRun(token, selectedRunId);
      onShowFeedback('评测执行完成！已生成 IR 指标与评估结果');
      onRunExecuted();
    } catch (err: any) {
      const msg = err.message || '执行评测失败';
      if (msg.includes('409') || msg.includes('already') || msg.includes('running')) {
        setActionError('当前评测任务已在执行中或已完成，不可重复执行 (409 Conflict)');
      } else {
        setActionError(msg);
      }
    } finally {
      setIsExecuting(false);
    }
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="h-3 w-3" /> 已完成
          </span>
        );
      case 'running':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-blue-500/10 px-2 py-0.5 text-xs font-medium text-blue-400 border border-blue-500/20">
            <Loader2 className="h-3 w-3 animate-spin" /> 执行中
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 px-2 py-0.5 text-xs font-medium text-rose-400 border border-rose-500/20">
            <XCircle className="h-3 w-3" /> 失败
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400 border border-amber-500/20">
            <Clock className="h-3 w-3" /> 待评测
          </span>
        );
    }
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-md mb-6">
      {actionError && (
        <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300 flex items-center justify-between">
          <span>{actionError}</span>
          <button
            onClick={() => setActionError('')}
            className="text-rose-400 hover:text-rose-200 font-bold ml-2"
          >
            ✕
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Dataset Selection */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Database className="h-3.5 w-3.5 text-blue-400" />
              基准测试集 (Dataset)
            </label>
            <button
              onClick={() => setShowCreateDataset(true)}
              className="flex items-center gap-1 text-xs font-medium text-blue-400 hover:text-blue-300 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> 新建测试集
            </button>
          </div>

          <div className="relative">
            <select
              value={selectedDatasetId || ''}
              onChange={(e) => onSelectDataset(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-800/90 px-3.5 py-2.5 text-sm text-slate-200 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {datasets.length === 0 ? (
                <option value="">暂无测试集，请点击右上角新建</option>
              ) : (
                datasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} {d.description ? `(${d.description})` : ''}
                  </option>
                ))
              )}
            </select>
          </div>
        </div>

        {/* Run Selection & Execution */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Layers className="h-3.5 w-3.5 text-indigo-400" />
              评测实验 (Evaluation Run)
            </label>
            <button
              disabled={!selectedDatasetId}
              onClick={() => setShowCreateRun(true)}
              className="flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Plus className="h-3.5 w-3.5" /> 新建 Run
            </button>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={selectedRunId || ''}
              onChange={(e) => onSelectRun(e.target.value)}
              disabled={!selectedDatasetId || runs.length === 0}
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800/90 px-3.5 py-2.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            >
              {runs.length === 0 ? (
                <option value="">当前测试集暂无 Run</option>
              ) : (
                runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} [{r.status}] (v{r.app_version})
                  </option>
                ))
              )}
            </select>

            {/* Execute Run Button */}
            {selectedRun && (
              <button
                disabled={isExecuting || selectedRun.status === 'completed' || selectedRun.status === 'running'}
                onClick={handleExecuteRun}
                className={`flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-xs font-medium transition-all shadow-md ${
                  selectedRun.status === 'completed'
                    ? 'bg-slate-800 text-slate-500 border border-slate-700/50 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-500/20 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> 执行评测中...
                  </>
                ) : selectedRun.status === 'completed' ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> 已评测
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5 fill-current" /> 执行评测
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Selected Run Details Bar */}
      {selectedRun && (
        <div className="mt-4 pt-3.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
          <div className="flex flex-wrap items-center gap-3">
            <span>状态: {renderStatusBadge(selectedRun.status)}</span>
            <span className="text-slate-600">|</span>
            <span>App 版本: <code className="text-slate-300 font-mono">v{selectedRun.app_version}</code></span>
            <span className="text-slate-600">|</span>
            <span>检索策略: <code className="text-indigo-300 font-mono">{selectedRun.retrieval_config?.search_mode || 'hybrid'}</code></span>
            <span className="text-slate-600">|</span>
            <span>Top K: <code className="text-slate-300 font-mono">{selectedRun.retrieval_config?.top_k || selectedRun.retrieval_config?.limit || 5}</code></span>
          </div>

          <div className="text-slate-500 text-[11px]">
            创建于: {new Date(selectedRun.created_at).toLocaleString()}
            {selectedRun.completed_at && ` · 完成于: ${new Date(selectedRun.completed_at).toLocaleTimeString()}`}
          </div>
        </div>
      )}

      {/* Create Dataset Dialog */}
      {showCreateDataset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-slate-100 mb-4 flex items-center gap-2">
              <Database className="h-4 w-4 text-blue-400" />
              新建基准测试集
            </h3>
            <form onSubmit={handleCreateDataset} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  测试集名称 *
                </label>
                <input
                  type="text"
                  required
                  value={newDatasetName}
                  onChange={(e) => setNewDatasetName(e.target.value)}
                  placeholder="例如: 技术偏好基准集 v1"
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  描述 (可选)
                </label>
                <textarea
                  rows={3}
                  value={newDatasetDesc}
                  onChange={(e) => setNewDatasetDesc(e.target.value)}
                  placeholder="说明该测试集的覆盖领域、用例规模及预期目标"
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-blue-500 focus:outline-none resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateDataset(false)}
                  className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isCreatingDataset || !newDatasetName.trim()}
                  className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-500 transition-colors disabled:opacity-50"
                >
                  {isCreatingDataset ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Run Dialog */}
      {showCreateRun && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-slate-100 mb-4 flex items-center gap-2">
              <Layers className="h-4 w-4 text-indigo-400" />
              新建评测实验 (Run)
            </h3>
            <form onSubmit={handleCreateRun} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  实验名称 *
                </label>
                <input
                  type="text"
                  required
                  value={newRunName}
                  onChange={(e) => setNewRunName(e.target.value)}
                  placeholder="例如: Hybrid Search Top-5 Benchmark"
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  检索策略 (Retrieval Strategy)
                </label>
                <select
                  value={newRunStrategy}
                  onChange={(e) => setNewRunStrategy(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="hybrid">混合检索 (Hybrid: Semantic + Keyword)</option>
                  <option value="semantic">纯向量语义检索 (Semantic pgvector)</option>
                  <option value="keyword">纯关键词匹配 (Keyword Match)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  返回条数 (Top-K)
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={newRunTopK}
                  onChange={(e) => setNewRunTopK(parseInt(e.target.value) || 5)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateRun(false)}
                  className="rounded-xl px-4 py-2 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isCreatingRun || !newRunName.trim()}
                  className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
                >
                  {isCreatingRun ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '创建实验'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  Info,
  Lock,
  Loader2,
  Layers,
  FileText,
  TrendingUp,
} from 'lucide-react';
import type { Memory, MemoryQualityResult, QualityDimensionScore } from '@/types';
import * as api from '@/lib/api';

interface Props {
  token: string;
}

export default function MemoryQualityViewer({ token }: Props) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [selectedMemoryId, setSelectedMemoryId] = useState<string>('');
  const [manualInputId, setManualInputId] = useState<string>('');
  const [qualityResult, setQualityResult] = useState<MemoryQualityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMemories, setLoadingMemories] = useState(false);
  const [error, setError] = useState('');

  // Load user memories for quick dropdown selection
  useEffect(() => {
    let mounted = true;
    setLoadingMemories(true);
    api
      .listMemories(token, { limit: 50 })
      .then((data) => {
        if (!mounted) return;
        setMemories(data);
        if (data.length > 0) {
          setSelectedMemoryId(data[0].id);
        }
      })
      .catch((err) => {
        if (!mounted) return;
        console.error('Failed to load memories for quality audit:', err);
      })
      .finally(() => {
        if (mounted) setLoadingMemories(false);
      });

    return () => {
      mounted = false;
    };
  }, [token]);

  // Evaluate memory quality
  const fetchQuality = useCallback(
    async (memId: string) => {
      if (!memId.trim()) return;
      setLoading(true);
      setError('');
      try {
        const res = await api.getMemoryQuality(token, memId.trim());
        setQualityResult(res);
      } catch (err: any) {
        setQualityResult(null);
        setError(err.message || '获取记忆质量评估失败，未找到该记忆或无权限');
      } finally {
        setLoading(false);
      }
    },
    [token]
  );

  useEffect(() => {
    if (selectedMemoryId) {
      fetchQuality(selectedMemoryId);
    }
  }, [selectedMemoryId, fetchQuality]);

  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (manualInputId.trim()) {
      setSelectedMemoryId(manualInputId.trim());
      fetchQuality(manualInputId.trim());
    }
  };

  const selectedMemoryObj = memories.find((m) => m.id === selectedMemoryId);

  // Helper for score badge
  const getTierInfo = (score: number) => {
    if (score >= 0.85) {
      return {
        label: '优秀 (Excellent)',
        color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
        barColor: 'bg-emerald-500',
      };
    }
    if (score >= 0.7) {
      return {
        label: '良好 (Good)',
        color: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
        barColor: 'bg-blue-500',
      };
    }
    if (score >= 0.5) {
      return {
        label: '合格 (Acceptable)',
        color: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
        barColor: 'bg-amber-500',
      };
    }
    if (score >= 0.3) {
      return {
        label: '待改进 (Needs Improvement)',
        color: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
        barColor: 'bg-orange-500',
      };
    }
    return {
      label: '高风险 (Critical)',
      color: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
      barColor: 'bg-rose-500',
    };
  };

  const DIMENSIONS_ORDER = [
    { key: 'confidence', label: 'Confidence (置信度)' },
    { key: 'importance', label: 'Importance (重要度)' },
    { key: 'freshness', label: 'Freshness (时效与新鲜度)' },
    { key: 'consistency', label: 'Consistency (语义一致性)' },
    { key: 'provenance', label: 'Provenance (溯源透明度)' },
    { key: 'duplication', label: 'Duplication (去重与冗余风险)' },
    { key: 'conflict_risk', label: 'Conflict Risk (冲突陈旧风险)' },
  ];

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-md mb-8">
      {/* Header with READ ONLY Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              Memory 确定性质量审查 (Quality Engine Viewer)
            </h3>
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2.5 py-0.5 text-[10px] font-semibold text-slate-300 border border-slate-700">
              <Lock className="h-3 w-3 text-amber-400" /> READ ONLY (严格只读审查)
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            由确定性算法实时量化 7 个维度的质量评分与置信度，不执行任何写操作，保证记忆实体不变性。
          </p>
        </div>

        {/* Memory Selector */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={selectedMemoryId}
            onChange={(e) => {
              setSelectedMemoryId(e.target.value);
              setManualInputId('');
            }}
            disabled={loadingMemories || memories.length === 0}
            className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none min-w-[220px]"
          >
            {memories.length === 0 ? (
              <option value="">暂无可用记忆</option>
            ) : (
              memories.map((m) => (
                <option key={m.id} value={m.id}>
                  [{m.category}] {m.key}: {m.content.slice(0, 24)}...
                </option>
              ))
            )}
          </select>

          {/* Manual ID Input */}
          <form onSubmit={handleManualSubmit} className="flex items-center gap-1">
            <input
              type="text"
              placeholder="输入 Memory ID 查询"
              value={manualInputId}
              onChange={(e) => setManualInputId(e.target.value)}
              className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-blue-500 focus:outline-none w-36 font-mono"
            />
            <button
              type="submit"
              className="rounded-xl bg-slate-800 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-700 transition-colors"
            >
              <Search className="h-3.5 w-3.5" />
            </button>
          </form>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-slate-400">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2 text-emerald-400" />
          <span className="text-xs">实时计算记忆确定性质量维度...</span>
        </div>
      ) : !qualityResult ? (
        <div className="py-10 text-center text-slate-500">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-xs">请选择上方记忆以审查质量维度得分与风险分析。</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Top Score Banner */}
          <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-5 flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="text-center bg-slate-900/80 rounded-2xl p-3 border border-slate-700/80 min-w-[90px]">
                <div className="text-3xl font-bold font-mono text-slate-100">
                  {qualityResult.overall_score.toFixed(2)}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider">总分 (Score)</div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                      getTierInfo(qualityResult.overall_score).color
                    }`}
                  >
                    {getTierInfo(qualityResult.overall_score).label}
                  </span>
                  <span className="text-xs text-slate-500 font-mono">
                    ID: {qualityResult.memory_id}
                  </span>
                </div>
                <p className="text-xs text-slate-300 font-medium">
                  {qualityResult.summary_reason || '该记忆质量综合评估正常。'}
                </p>
              </div>
            </div>

            {selectedMemoryObj && (
              <div className="text-right text-xs text-slate-400 max-w-sm">
                <div className="text-[11px] text-slate-500">审查目标内容:</div>
                <div className="text-slate-300 italic line-clamp-2 mt-0.5">
                  &ldquo;{selectedMemoryObj.content}&rdquo;
                </div>
              </div>
            )}
          </div>

          {/* Actionable Warnings */}
          {qualityResult.warnings && qualityResult.warnings.length > 0 && (
            <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
              <h4 className="text-xs font-semibold text-amber-300 flex items-center gap-1.5 mb-2">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                质量警告与潜在风险 (Warnings)
              </h4>
              <ul className="space-y-1.5 text-xs text-amber-400/90">
                {qualityResult.warnings.map((w, idx) => (
                  <li key={idx} className="flex items-center gap-1.5">
                    <span className="text-amber-500">•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 7 Quality Dimensions Breakdown */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-400" />
              7 项量化质量维度详细分析 (Dimensions Breakdown)
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {DIMENSIONS_ORDER.map(({ key, label }) => {
                const dim: QualityDimensionScore | undefined = qualityResult.dimensions[key];
                if (!dim) return null;

                const percent = Math.min(100, Math.max(0, dim.score * 100));

                return (
                  <div
                    key={key}
                    className="rounded-xl border border-slate-800/80 bg-slate-850/50 p-3.5 hover:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1.5 text-xs">
                      <span className="font-semibold text-slate-200">{label}</span>
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-slate-500 text-[11px]">
                          权重: {(dim.weight * 100).toFixed(0)}%
                        </span>
                        <span className="text-slate-100 font-bold">
                          {dim.score.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Progress bar */}
                    <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden mb-2">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          dim.score >= 0.8
                            ? 'bg-emerald-500'
                            : dim.score >= 0.5
                            ? 'bg-blue-500'
                            : 'bg-amber-500'
                        }`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>

                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      {dim.reason}
                    </p>

                    {dim.raw_risk !== null && dim.raw_risk !== undefined && (
                      <div className="mt-1.5 text-[10px] text-slate-500 font-mono">
                        底层风险值 (Raw Risk): {dim.raw_risk.toFixed(3)}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Footer Notice */}
          <div className="pt-3 border-t border-slate-800/80 text-right text-[11px] text-slate-500">
            评估时间戳: {new Date(qualityResult.evaluated_at).toLocaleString()} · 引擎保证无副作用只读
          </div>
        </div>
      )}
    </div>
  );
}

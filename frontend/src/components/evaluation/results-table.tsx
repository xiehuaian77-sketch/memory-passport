'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ListFilter,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Search,
  ExternalLink,
} from 'lucide-react';
import type { EvaluationResult } from '@/types';
import * as api from '@/lib/api';

interface Props {
  token: string;
  runId: string | null;
}

const PAGE_SIZE = 10;

export default function ResultsTable({ token, runId }: Props) {
  const [results, setResults] = useState<EvaluationResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  const fetchResults = useCallback(async () => {
    if (!runId) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const offset = (page - 1) * PAGE_SIZE;
      const data = await api.listEvaluationRunResults(token, runId, offset, PAGE_SIZE + 1);
      if (data.length > PAGE_SIZE) {
        setHasMore(true);
        setResults(data.slice(0, PAGE_SIZE));
      } else {
        setHasMore(false);
        setResults(data);
      }
    } catch (err: any) {
      setError(err.message || '加载评测用例结果失败');
    } finally {
      setLoading(false);
    }
  }, [token, runId, page]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  // Reset page when runId changes
  useEffect(() => {
    setPage(1);
  }, [runId]);

  if (!runId) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-md mb-8">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <ListFilter className="h-4 w-4 text-blue-400" />
            用例级评测明细表 (Case-Level Results)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            审查每个测试用例检索返回的 Top-K 记忆、预期相关记忆及精确率指标。
          </p>
        </div>

        {/* Pagination Controls */}
        <div className="flex items-center gap-2 text-xs">
          <button
            disabled={page <= 1 || loading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> 上一页
          </button>
          <span className="font-mono text-slate-400 px-1">第 {page} 页</span>
          <button
            disabled={!hasMore || loading}
            onClick={() => setPage((p) => p + 1)}
            className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            下一页 <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-slate-400">
          <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2 text-blue-400" />
          <span className="text-xs">加载用例结果中...</span>
        </div>
      ) : results.length === 0 ? (
        <div className="py-12 text-center text-slate-500">
          <Search className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-xs">该实验暂无用例评测结果（或尚未执行完毕）。</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-medium">
                <th className="py-3 px-3 w-16">状态</th>
                <th className="py-3 px-3 min-w-[200px]">测试查询 / Case ID</th>
                <th className="py-3 px-3 min-w-[180px]">检索返回 Memory IDs</th>
                <th className="py-3 px-3 min-w-[120px]">命中指标 (Metrics)</th>
                <th className="py-3 px-3 w-24 text-right">耗时</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {results.map((res) => {
                const rr = res.metrics?.reciprocal_rank;
                const p = res.metrics?.precision;
                const r = res.metrics?.recall;

                return (
                  <tr key={res.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-3">
                      {res.passed ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400 font-medium" title="Passed">
                          <CheckCircle2 className="h-4 w-4" />
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-slate-500" title="Missed ground truth">
                          <XCircle className="h-4 w-4" />
                        </span>
                      )}
                    </td>

                    <td className="py-3 px-3">
                      <div className="font-medium text-slate-200 line-clamp-2" title={res.case_id}>
                        {res.details?.query || `Case #${res.case_id.slice(0, 8)}`}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                        ID: {res.case_id}
                      </div>
                    </td>

                    <td className="py-3 px-3">
                      {res.retrieved_memory_ids.length === 0 ? (
                        <span className="text-slate-600 font-mono text-[11px]">未召回记忆</span>
                      ) : (
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {res.retrieved_memory_ids.map((id, idx) => (
                            <span
                              key={id}
                              className="inline-block rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 border border-slate-700"
                              title={`Memory ID: ${id}`}
                            >
                              #{idx + 1}: {id.slice(0, 8)}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>

                    <td className="py-3 px-3 font-mono text-[11px]">
                      <div className="space-y-0.5">
                        {typeof rr === 'number' && (
                          <div className="text-amber-400">RR: {rr.toFixed(3)}</div>
                        )}
                        {typeof p === 'number' && (
                          <div className="text-blue-300">P: {(p * 100).toFixed(0)}%</div>
                        )}
                        {typeof r === 'number' && (
                          <div className="text-emerald-300">R: {(r * 100).toFixed(0)}%</div>
                        )}
                      </div>
                    </td>

                    <td className="py-3 px-3 text-right font-mono text-slate-300">
                      {res.latency_ms.toFixed(1)} ms
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

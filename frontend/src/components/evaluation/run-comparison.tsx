'use client';

import { useState } from 'react';
import {
  GitCompare,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  CheckCircle2,
  Sliders,
  Sparkles,
  Layers,
  HelpCircle,
} from 'lucide-react';
import type { EvaluationRun } from '@/types';

interface Props {
  runs: EvaluationRun[];
  datasetName?: string;
}

export default function RunComparison({ runs, datasetName }: Props) {
  // Only completed runs can be meaningfully compared
  const completedRuns = runs.filter((r) => r.status === 'completed' && r.summary_metrics);

  const [selectedRunIds, setSelectedRunIds] = useState<string[]>(() => {
    // Default to first 2 completed runs if available
    return completedRuns.slice(0, 2).map((r) => r.id);
  });

  const toggleRun = (id: string) => {
    if (selectedRunIds.includes(id)) {
      if (selectedRunIds.length <= 1) return; // keep at least 1 selected
      setSelectedRunIds(selectedRunIds.filter((x) => x !== id));
    } else {
      if (selectedRunIds.length >= 4) {
        // limit to 4 for readability
        setSelectedRunIds([...selectedRunIds.slice(1), id]);
      } else {
        setSelectedRunIds([...selectedRunIds, id]);
      }
    }
  };

  if (completedRuns.length < 2) {
    return (
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/30 p-8 text-center backdrop-blur-md mb-6">
        <GitCompare className="h-10 w-10 text-slate-600 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-300 mb-1">无可对比的评测实验</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          多版本对比分析至少需要 2 个已完成（Completed）且具备评估指标的评测实验。请先在上方新建并执行实验。
        </p>
      </div>
    );
  }

  const comparedRuns = completedRuns.filter((r) => selectedRunIds.includes(r.id));

  // Helpers for extracting numeric metric values
  const getMetricVal = (run: EvaluationRun, path: string): number | null => {
    const sm = run.summary_metrics;
    if (!sm) return null;
    if (path === 'mrr') return typeof sm.mrr === 'number' ? sm.mrr : null;
    if (path === 'map') return typeof sm.map === 'number' ? sm.map : null;
    if (path === 'latency') {
      return typeof sm.avg_latency_ms === 'number'
        ? sm.avg_latency_ms
        : typeof sm.latency_ms === 'number'
        ? sm.latency_ms
        : null;
    }
    if (path.startsWith('p@')) {
      const k = path.replace('p@', '');
      const p = sm.precision_at_k || {};
      const val = p[k] ?? p[parseInt(k)];
      return typeof val === 'number' ? val : null;
    }
    if (path.startsWith('r@')) {
      const k = path.replace('r@', '');
      const r = sm.recall_at_k || {};
      const val = r[k] ?? r[parseInt(k)];
      return typeof val === 'number' ? val : null;
    }
    if (path.startsWith('ndcg@')) {
      const k = path.replace('ndcg@', '');
      const ndcg = sm.ndcg_at_k || {};
      const val = ndcg[k] ?? ndcg[parseInt(k)];
      return typeof val === 'number' ? val : null;
    }
    return null;
  };

  const METRICS_LIST = [
    { key: 'mrr', label: 'MRR (平均倒数排名)', higherIsBetter: true, format: (v: number) => v.toFixed(3) },
    { key: 'p@1', label: 'Precision@1', higherIsBetter: true, format: (v: number) => (v * 100).toFixed(1) + '%' },
    { key: 'p@5', label: 'Precision@5', higherIsBetter: true, format: (v: number) => (v * 100).toFixed(1) + '%' },
    { key: 'r@1', label: 'Recall@1', higherIsBetter: true, format: (v: number) => (v * 100).toFixed(1) + '%' },
    { key: 'r@5', label: 'Recall@5', higherIsBetter: true, format: (v: number) => (v * 100).toFixed(1) + '%' },
    { key: 'ndcg@5', label: 'NDCG@5', higherIsBetter: true, format: (v: number) => v.toFixed(3) },
    { key: 'ndcg@10', label: 'NDCG@10', higherIsBetter: true, format: (v: number) => v.toFixed(3) },
    { key: 'latency', label: 'Avg Latency (平均耗时)', higherIsBetter: false, format: (v: number) => `${v.toFixed(1)} ms` },
  ];

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-md mb-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
            <GitCompare className="h-4 w-4 text-indigo-400" />
            多策略 / 多版本评测对比 (Run Comparison)
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">
            横向对比不同检索配置（Hybrid、Semantic、Keyword）或不同 App 版本的命中率与耗时差异。
          </p>
        </div>

        {/* Run selector pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 mr-1">选择对比项:</span>
          {completedRuns.map((r) => {
            const isSelected = selectedRunIds.includes(r.id);
            return (
              <button
                key={r.id}
                onClick={() => toggleRun(r.id)}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20 border border-indigo-400'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200 border border-slate-700'
                }`}
              >
                {r.name} (v{r.app_version})
              </button>
            );
          })}
        </div>
      </div>

      {/* Comparison Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400">
              <th className="py-3 px-3 w-48 font-medium">评估维度 / 参数</th>
              {comparedRuns.map((r) => (
                <th key={r.id} className="py-3 px-3 font-semibold text-slate-200">
                  <div className="flex items-center gap-1.5">
                    <span className="text-indigo-400">●</span>
                    <span className="truncate max-w-[180px]" title={r.name}>{r.name}</span>
                  </div>
                  <div className="text-[11px] text-slate-500 font-mono font-normal">
                    v{r.app_version} · {r.retrieval_config?.search_mode || 'hybrid'}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {/* Configuration Summary Row */}
            <tr className="bg-slate-800/20 text-slate-400">
              <td className="py-2.5 px-3 font-medium flex items-center gap-1.5 text-slate-300">
                <Sliders className="h-3.5 w-3.5 text-slate-400" /> 检索配置 (Config)
              </td>
              {comparedRuns.map((r) => (
                <td key={r.id} className="py-2.5 px-3 font-mono text-[11px] text-slate-300">
                  mode: {r.retrieval_config?.search_mode || 'hybrid'} | top_k: {r.retrieval_config?.top_k || 5}
                </td>
              ))}
            </tr>

            {/* Metrics Rows */}
            {METRICS_LIST.map(({ key, label, higherIsBetter, format }) => {
              // Find best value across compared runs
              const values = comparedRuns.map((r) => getMetricVal(r, key));
              const validValues = values.filter((v): v is number => v !== null);
              const bestVal =
                validValues.length > 0
                  ? higherIsBetter
                    ? Math.max(...validValues)
                    : Math.min(...validValues)
                  : null;

              return (
                <tr key={key} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-2.5 px-3 font-medium text-slate-300">{label}</td>
                  {comparedRuns.map((r) => {
                    const val = getMetricVal(r, key);
                    const isBest = val !== null && bestVal !== null && val === bestVal && validValues.length > 1;

                    return (
                      <td key={r.id} className="py-2.5 px-3 font-mono">
                        {val !== null ? (
                          <span
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${
                              isBest
                                ? 'bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/20'
                                : 'text-slate-300'
                            }`}
                          >
                            {format(val)}
                            {isBest && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                          </span>
                        ) : (
                          <span className="text-slate-600">-</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Summary Note */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          绿色高亮代表该维度下的最优表现实验（Higher is better for accuracy, Lower is better for latency）。
        </span>
        <span>
          当前对比项: <code className="text-slate-400 font-mono">{comparedRuns.length}</code> 个 Runs
        </span>
      </div>
    </div>
  );
}

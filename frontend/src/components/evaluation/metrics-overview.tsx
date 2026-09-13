'use client';

import {
  TrendingUp,
  Target,
  Zap,
  Award,
  BarChart2,
  Clock,
  AlertCircle,
  Activity,
  Layers,
  Sparkles,
} from 'lucide-react';
import type { EvaluationRun } from '@/types';

interface Props {
  run: EvaluationRun | null;
  metrics: Record<string, any> | null;
  loading: boolean;
}

export default function MetricsOverview({ run, metrics, loading }: Props) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-center backdrop-blur-md mb-6 animate-pulse">
        <Activity className="h-8 w-8 text-slate-600 mx-auto mb-3 animate-spin" />
        <p className="text-sm text-slate-400">加载评测指标中...</p>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/30 p-10 text-center backdrop-blur-md mb-6">
        <Layers className="h-10 w-10 text-slate-600 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-300 mb-1">未选择评测实验</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto">
          请在上方选择或新建一个评测实验（Run）以查看详细的信息检索（IR）与质量量化指标。
        </p>
      </div>
    );
  }

  if (run.status === 'pending') {
    return (
      <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-8 text-center backdrop-blur-md mb-6">
        <Clock className="h-10 w-10 text-amber-400/80 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-amber-200 mb-1">评测实验尚未执行</h3>
        <p className="text-xs text-amber-400/70 max-w-md mx-auto mb-4">
          该 Run 当前状态为 Pending，尚未进行 retrieval pipeline 执行与得分计算。请点击上方「执行评测」按钮开始基准测试。
        </p>
      </div>
    );
  }

  if (run.status === 'failed') {
    return (
      <div className="rounded-2xl border border-rose-500/20 bg-rose-500/5 p-8 text-center backdrop-blur-md mb-6">
        <AlertCircle className="h-10 w-10 text-rose-400 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-rose-200 mb-1">评测任务执行失败</h3>
        <p className="text-xs text-rose-400/80 max-w-md mx-auto font-mono">
          {run.error_message || '执行遇到未处理异常，请检查配置或重试。'}
        </p>
      </div>
    );
  }

  if (!metrics || Object.keys(metrics).length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/30 p-8 text-center backdrop-blur-md mb-6">
        <AlertCircle className="h-8 w-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-400">暂无指标数据</p>
      </div>
    );
  }

  // Extract metrics from API response
  const mrr = typeof metrics.mrr === 'number' ? metrics.mrr : null;
  const mapScore = typeof metrics.map === 'number' ? metrics.map : null;
  const avgLatency =
    typeof metrics.avg_latency_ms === 'number'
      ? metrics.avg_latency_ms
      : typeof metrics.latency_ms === 'number'
      ? metrics.latency_ms
      : null;
  const totalCases = typeof metrics.total_cases === 'number' ? metrics.total_cases : null;

  const pAtK = metrics.precision_at_k || {};
  const rAtK = metrics.recall_at_k || {};
  const ndcgAtK = metrics.ndcg_at_k || {};

  const formatRate = (v: any) => {
    if (typeof v !== 'number') return 'N/A';
    return (v * 100).toFixed(1) + '%';
  };

  const formatScore = (v: any) => {
    if (typeof v !== 'number') return 'N/A';
    return v.toFixed(3);
  };

  return (
    <div className="space-y-6 mb-8">
      {/* Top Core IR Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* MRR Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">MRR</span>
            <Award className="h-4 w-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 mb-1 font-mono">
            {formatScore(mrr)}
          </div>
          <div className="text-[11px] text-slate-500 mb-2">Mean Reciprocal Rank (平均倒数排名)</div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-400 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(0, (mrr || 0) * 100))}%` }}
            />
          </div>
        </div>

        {/* Precision@5 Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Precision@5</span>
            <Target className="h-4 w-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 mb-1 font-mono">
            {formatRate(pAtK['5'] ?? pAtK[5])}
          </div>
          <div className="text-[11px] text-slate-500 mb-2">前 5 条结果中真正相关记忆占比</div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(0, ((pAtK['5'] ?? pAtK[5]) || 0) * 100))}%` }}
            />
          </div>
        </div>

        {/* Recall@5 Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Recall@5</span>
            <TrendingUp className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 mb-1 font-mono">
            {formatRate(rAtK['5'] ?? rAtK[5])}
          </div>
          <div className="text-[11px] text-slate-500 mb-2">标准答案中被检索出的覆盖率</div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(0, ((rAtK['5'] ?? rAtK[5]) || 0) * 100))}%` }}
            />
          </div>
        </div>

        {/* Latency Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-lg backdrop-blur-sm">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider">Avg Latency</span>
            <Zap className="h-4 w-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100 mb-1 font-mono">
            {avgLatency !== null ? `${avgLatency.toFixed(1)} ms` : 'N/A'}
          </div>
          <div className="text-[11px] text-slate-500 mb-2">
            {avgLatency !== null && avgLatency < 50
              ? '⚡ 响应极速 (<50ms)'
              : avgLatency !== null && avgLatency < 150
              ? '✓ 响应良好 (<150ms)'
              : '评测样本检索耗时'}
          </div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(10, (avgLatency ? 200 - avgLatency : 100) / 2))}%` }}
            />
          </div>
        </div>
      </div>

      {/* Detailed IR Metrics Breakdown (P@K, R@K, NDCG@K) */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-xl backdrop-blur-md">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
          <BarChart2 className="h-4 w-4 text-indigo-400" />
          分层检索质量指标 (Multi-Cutoff Quality Breakdown)
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Precision @ K */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-4">
            <div className="text-xs font-medium text-slate-300 mb-3 flex items-center justify-between">
              <span>Precision @ K</span>
              <span className="text-[10px] text-slate-500 font-mono">P@1, 3, 5, 10</span>
            </div>
            <div className="space-y-2.5">
              {[1, 3, 5, 10].map((k) => {
                const val = pAtK[String(k)] ?? pAtK[k];
                return (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <span className="w-10 text-slate-400 font-mono">@{k}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(0, (val || 0) * 100))}%` }}
                      />
                    </div>
                    <span className="w-14 text-right font-mono text-slate-200">
                      {val !== undefined ? (val * 100).toFixed(1) + '%' : '-'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recall @ K */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-4">
            <div className="text-xs font-medium text-slate-300 mb-3 flex items-center justify-between">
              <span>Recall @ K</span>
              <span className="text-[10px] text-slate-500 font-mono">R@1, 3, 5, 10</span>
            </div>
            <div className="space-y-2.5">
              {[1, 3, 5, 10].map((k) => {
                const val = rAtK[String(k)] ?? rAtK[k];
                return (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <span className="w-10 text-slate-400 font-mono">@{k}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(0, (val || 0) * 100))}%` }}
                      />
                    </div>
                    <span className="w-14 text-right font-mono text-slate-200">
                      {val !== undefined ? (val * 100).toFixed(1) + '%' : '-'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* NDCG @ K */}
          <div className="rounded-xl border border-slate-800/80 bg-slate-800/40 p-4">
            <div className="text-xs font-medium text-slate-300 mb-3 flex items-center justify-between">
              <span>NDCG @ K</span>
              <span className="text-[10px] text-slate-500 font-mono">NDCG@3, 5, 10</span>
            </div>
            <div className="space-y-2.5">
              {[3, 5, 10].map((k) => {
                const val = ndcgAtK[String(k)] ?? ndcgAtK[k];
                return (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <span className="w-10 text-slate-400 font-mono">@{k}</span>
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${Math.min(100, Math.max(0, (val || 0) * 100))}%` }}
                      />
                    </div>
                    <span className="w-14 text-right font-mono text-slate-200">
                      {val !== undefined ? val.toFixed(3) : '-'}
                    </span>
                  </div>
                );
              })}
              {mapScore !== null && (
                <div className="pt-2 border-t border-slate-700/50 flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-medium">MAP (Mean Avg Precision):</span>
                  <span className="font-mono text-indigo-300 font-bold">{mapScore.toFixed(3)}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {totalCases !== null && (
          <div className="mt-4 pt-3 border-t border-slate-800/80 text-right text-[11px] text-slate-500">
            评测用例规模: <span className="font-semibold text-slate-300">{totalCases}</span> 个测试查询
          </div>
        )}
      </div>
    </div>
  );
}

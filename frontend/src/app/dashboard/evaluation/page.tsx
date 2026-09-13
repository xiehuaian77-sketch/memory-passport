'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import {
  BarChart3,
  GitCompare,
  ShieldCheck,
  Activity,
  Layers,
  Sparkles,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import type { EvaluationDataset, EvaluationRun } from '@/types';
import Navbar from '@/components/navbar';

import DatasetRunSelector from '@/components/evaluation/dataset-run-selector';
import MetricsOverview from '@/components/evaluation/metrics-overview';
import RunComparison from '@/components/evaluation/run-comparison';
import ResultsTable from '@/components/evaluation/results-table';
import MemoryQualityViewer from '@/components/evaluation/memory-quality-viewer';

type Tab = 'overview' | 'comparison' | 'quality';

function EvaluationContent() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();

  // Navigation tab
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  // Datasets and Runs state
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [runs, setRuns] = useState<EvaluationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runMetrics, setRunMetrics] = useState<Record<string, any> | null>(null);

  // Loading & error states
  const [loadingDatasets, setLoadingDatasets] = useState(true);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const showFeedback = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(''), 4000);
  };

  // Auth guard
  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  // Load Datasets
  const fetchDatasets = useCallback(async () => {
    if (!token) return;
    setLoadingDatasets(true);
    setError('');
    try {
      const data = await api.listEvaluationDatasets(token);
      setDatasets(data);
      if (data.length > 0 && !selectedDatasetId) {
        setSelectedDatasetId(data[0].id);
      }
    } catch (err: any) {
      setError(err.message || '加载评测数据集失败');
    } finally {
      setLoadingDatasets(false);
    }
  }, [token, selectedDatasetId]);

  useEffect(() => {
    if (token) {
      fetchDatasets();
    }
  }, [token, fetchDatasets]);

  // Load Runs for selected dataset
  const fetchRuns = useCallback(async () => {
    if (!token || !selectedDatasetId) {
      setRuns([]);
      setSelectedRunId(null);
      return;
    }
    setLoadingRuns(true);
    try {
      const data = await api.listEvaluationRuns(token, selectedDatasetId);
      setRuns(data);
      if (data.length > 0) {
        // Keep selection if exists, else select first
        if (!selectedRunId || !data.some((r) => r.id === selectedRunId)) {
          setSelectedRunId(data[0].id);
        }
      } else {
        setSelectedRunId(null);
        setRunMetrics(null);
      }
    } catch (err: any) {
      setError(err.message || '加载评测实验列表失败');
    } finally {
      setLoadingRuns(false);
    }
  }, [token, selectedDatasetId, selectedRunId]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Load Metrics for selected run
  const fetchRunMetrics = useCallback(async () => {
    if (!token || !selectedRunId) {
      setRunMetrics(null);
      return;
    }
    const currentRun = runs.find((r) => r.id === selectedRunId);
    if (!currentRun || currentRun.status !== 'completed') {
      setRunMetrics(null);
      return;
    }

    // If summary_metrics is already populated in run, use it; else fetch from API
    if (currentRun.summary_metrics) {
      setRunMetrics(currentRun.summary_metrics);
      return;
    }

    setLoadingMetrics(true);
    try {
      const data = await api.getEvaluationRunMetrics(token, selectedRunId);
      setRunMetrics(data);
    } catch (err: any) {
      console.error('Failed to fetch run metrics:', err);
      setRunMetrics(null);
    } finally {
      setLoadingMetrics(false);
    }
  }, [token, selectedRunId, runs]);

  useEffect(() => {
    fetchRunMetrics();
  }, [fetchRunMetrics]);

  const selectedDataset = datasets.find((d) => d.id === selectedDatasetId);
  const selectedRun = runs.find((r) => r.id === selectedRunId);

  if (isLoading || (loadingDatasets && datasets.length === 0)) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
        <Activity className="h-6 w-6 animate-spin text-blue-400 mr-2" />
        <span className="text-sm">加载评测中心组件...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16 pt-20">
      <Navbar />

      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
              <BarChart3 className="h-6 w-6 text-indigo-400" />
              评测与质量监控中心
              <span className="rounded-full bg-indigo-500/10 px-2.5 py-0.5 text-xs font-semibold text-indigo-400 border border-indigo-500/20">
                Evaluation & Quality Engine
              </span>
            </h1>
            <p className="mt-1 text-xs sm:text-sm text-slate-400 max-w-2xl">
              提供标准化的 Information Retrieval (IR) 指标度量、多实验对比（Precision / Recall / MRR / NDCG）及 Memory 确定性质量审查。
            </p>
          </div>

          <button
            onClick={() => {
              fetchDatasets();
              fetchRuns();
              fetchRunMetrics();
              showFeedback('数据已刷新');
            }}
            className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" /> 刷新数据
          </button>
        </div>

        {/* Global Feedback Toast */}
        {feedback && (
          <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-300 shadow-lg flex items-center justify-between animate-fadeIn">
            <span>{feedback}</span>
            <button onClick={() => setFeedback('')} className="text-emerald-400 font-bold ml-2">✕</button>
          </div>
        )}

        {/* Global Error Banner */}
        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300 shadow-lg flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError('')} className="text-rose-400 font-bold ml-2">✕</button>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 mb-6 gap-2">
          <button
            onClick={() => setActiveTab('overview')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs sm:text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'overview'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            综合评测概览 (Overview)
          </button>

          <button
            onClick={() => setActiveTab('comparison')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs sm:text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'comparison'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <GitCompare className="h-4 w-4" />
            多实验版本对比 (Run Comparison)
          </button>

          <button
            onClick={() => setActiveTab('quality')}
            className={`flex items-center gap-2 pb-3 px-3 text-xs sm:text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'quality'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
            记忆确定性质量审查 (Quality Viewer)
          </button>
        </div>

        {/* Tab 1: Overview */}
        {activeTab === 'overview' && (
          <div>
            {/* Dataset & Run Selector */}
            {token && (
              <DatasetRunSelector
                token={token}
                datasets={datasets}
                selectedDatasetId={selectedDatasetId}
                onSelectDataset={(id) => setSelectedDatasetId(id)}
                onDatasetCreated={fetchDatasets}
                runs={runs}
                selectedRunId={selectedRunId}
                onSelectRun={(id) => setSelectedRunId(id)}
                onRunCreated={fetchRuns}
                onRunExecuted={() => {
                  fetchRuns();
                  fetchRunMetrics();
                }}
                onShowFeedback={showFeedback}
              />
            )}

            {/* Metrics Overview Cards & Breakdown */}
            <MetricsOverview
              run={selectedRun || null}
              metrics={runMetrics}
              loading={loadingMetrics}
            />

            {/* Detailed Per-Case Results Table */}
            {token && (
              <ResultsTable token={token} runId={selectedRunId} />
            )}
          </div>
        )}

        {/* Tab 2: Run Comparison */}
        {activeTab === 'comparison' && (
          <div>
            {token && (
              <DatasetRunSelector
                token={token}
                datasets={datasets}
                selectedDatasetId={selectedDatasetId}
                onSelectDataset={(id) => setSelectedDatasetId(id)}
                onDatasetCreated={fetchDatasets}
                runs={runs}
                selectedRunId={selectedRunId}
                onSelectRun={(id) => setSelectedRunId(id)}
                onRunCreated={fetchRuns}
                onRunExecuted={() => {
                  fetchRuns();
                  fetchRunMetrics();
                }}
                onShowFeedback={showFeedback}
              />
            )}

            <RunComparison
              runs={runs}
              datasetName={selectedDataset?.name}
            />
          </div>
        )}

        {/* Tab 3: Memory Quality Viewer */}
        {activeTab === 'quality' && (
          <div>
            {token && <MemoryQualityViewer token={token} />}
          </div>
        )}
      </main>
    </div>
  );
}

export default function EvaluationPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-400">
          <Activity className="h-6 w-6 animate-spin text-blue-400 mr-2" />
          <span className="text-sm">加载评测中心...</span>
        </div>
      }
    >
      <EvaluationContent />
    </Suspense>
  );
}

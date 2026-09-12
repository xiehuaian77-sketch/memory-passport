'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Settings,
  Shield,
  Bot,
  Brain,
  CheckCircle2,
  Lock,
  Save,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import type { UserMemoryPolicy } from '@/types';
import * as api from '@/lib/api';

export default function SettingsPage() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();

  const [policy, setPolicy] = useState<UserMemoryPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!token) return;
    let isMounted = true;
    async function loadPolicy() {
      try {
        setLoading(true);
        setError('');
        const data = await api.getMemoryPolicy(token!);
        if (isMounted) {
          setPolicy(data);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : '加载策略失败');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadPolicy();
    return () => {
      isMounted = false;
    };
  }, [token]);

  const handleToggle = (key: keyof UserMemoryPolicy) => {
    if (!policy) return;
    if (key === 'require_confirmation') {
      // Human-in-the-loop: locked for safety
      return;
    }
    setPolicy({
      ...policy,
      [key]: !policy[key],
    });
  };

  const handleSave = async () => {
    if (!token || !policy) return;
    try {
      setSaving(true);
      setError('');
      const updated = await api.updateMemoryPolicy(token, {
        memory_enabled: policy.memory_enabled,
        allow_memory_retrieval: policy.allow_memory_retrieval,
        allow_ai_extraction: policy.allow_ai_extraction,
        require_confirmation: policy.require_confirmation,
      });
      setPolicy(updated);
      setFeedback('记忆策略与治理配置已成功更新，并在全系统即时生效！');
      setTimeout(() => setFeedback(''), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新配置失败');
    } finally {
      setSaving(false);
    }
  };

  if (isLoading || !user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <Settings className="h-6 w-6 text-blue-400" />
            记忆策略与治理设置
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            定义 AI 助手如何访问、检索以及从对话中发现你的长期记忆。
          </p>
        </div>

        <button
          onClick={handleSave}
          disabled={loading || saving || !policy}
          className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-blue-600/20 hover:bg-blue-500 disabled:opacity-50 transition-all"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          保存策略
        </button>
      </div>

      {/* Feedback Messages */}
      {feedback && (
        <div className="mb-6 flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm text-emerald-300 animate-fade-in">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          {feedback}
        </div>
      )}

      {error && (
        <div className="mb-6 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-900/20 p-4 text-sm text-red-400 animate-fade-in">
          <AlertCircle className="h-5 w-5 text-red-400 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
          <p className="mt-3 text-xs text-slate-500">正在读取用户记忆策略...</p>
        </div>
      ) : policy ? (
        <div className="space-y-4">
          {/* Policy Card 1: Master switch */}
          <div className="rounded-2xl border border-slate-700 bg-slate-800/40 p-5 shadow-lg">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-blue-600/20 p-2 text-blue-400 border border-blue-500/30 mt-0.5">
                  <Brain className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-100">
                    全局记忆系统 (Memory System)
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    控制个人长期记忆库的整体运作。关闭后，系统将停用长期记忆检索与提炼能力，AI 将仅依据单次会话历史回答。
                  </p>
                </div>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                onClick={() => handleToggle('memory_enabled')}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  policy.memory_enabled ? 'bg-blue-600' : 'bg-slate-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    policy.memory_enabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Policy Card 2: Retrieval in chat */}
          <div className="rounded-2xl border border-slate-700 bg-slate-800/40 p-5 shadow-lg">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-cyan-600/20 p-2 text-cyan-400 border border-cyan-500/30 mt-0.5">
                  <Shield className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-100">
                    对话记忆检索 (Memory Retrieval in Chat)
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    允许 AI 在接收到你的问题时，自动检索库内高相关度的偏好与事实，精准辅助生成个性化回复。
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={!policy.memory_enabled}
                onClick={() => handleToggle('allow_memory_retrieval')}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40 ${
                  policy.allow_memory_retrieval && policy.memory_enabled
                    ? 'bg-blue-600'
                    : 'bg-slate-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    policy.allow_memory_retrieval && policy.memory_enabled
                      ? 'translate-x-5'
                      : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Policy Card 3: AI Extraction */}
          <div className="rounded-2xl border border-slate-700 bg-slate-800/40 p-5 shadow-lg">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-purple-600/20 p-2 text-purple-400 border border-purple-500/30 mt-0.5">
                  <Bot className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-slate-100">
                    智能记忆提炼 (AI Memory Extraction)
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    允许从对话历史中挖掘并提炼新的候选事实。提炼出的条目将放入你的「收件箱」，绝不会静默自动落库。
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={!policy.memory_enabled}
                onClick={() => handleToggle('allow_ai_extraction')}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:opacity-40 ${
                  policy.allow_ai_extraction && policy.memory_enabled
                    ? 'bg-blue-600'
                    : 'bg-slate-700'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                    policy.allow_ai_extraction && policy.memory_enabled
                      ? 'translate-x-5'
                      : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Policy Card 4: Require Confirmation (Locked for Safety) */}
          <div className="rounded-2xl border border-slate-700 bg-slate-800/40 p-5 shadow-lg opacity-90">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-emerald-600/20 p-2 text-emerald-400 border border-emerald-500/30 mt-0.5">
                  <Lock className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-slate-100">
                      入库强制人工确认 (Human-in-the-loop Confirmation)
                    </h3>
                    <span className="rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.2 text-[10px] font-semibold text-emerald-300">
                      核心安全锁定
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                    最高安全基线：AI 永远只能提出「候选记忆」，绝不允许在未经你显式授权确认的情况下直接写入长期记忆库。
                  </p>
                </div>
              </div>

              {/* Locked Active State */}
              <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium bg-emerald-950/60 border border-emerald-500/30 rounded-lg px-3 py-1">
                <CheckCircle2 className="h-3.5 w-3.5" /> 始终开启
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

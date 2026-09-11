'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Fingerprint,
  Mail,
  Wallet,
  Shield,
  Download,
  Trash2,
  Copy,
  CheckCircle,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import { formatDate } from '@/lib/utils';

export default function IdentityPage() {
  const { user, token, isLoading, logout, refreshUser } = useAuth();
  const router = useRouter();
  const [copied, setCopied] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
      return;
    }
    if (user) setDisplayName(user.display_name);
  }, [isLoading, user, router]);

  const copyPassportId = () => {
    if (!user) return;
    navigator.clipboard.writeText(user.passport_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleUpdateProfile = async () => {
    if (!token || !displayName.trim()) return;
    setSaving(true);
    try {
      const res = await fetch('/api/auth/me', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ display_name: displayName }),
      });
      if (!res.ok) throw new Error('更新失败');
      await refreshUser();
    } catch {
      alert('更新失败');
    } finally {
      setSaving(false);
    }
  };

  const handleExportAll = async () => {
    if (!token) return;
    try {
      const data = await api.exportMemories(token);
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `memory-passport-full-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('导出失败');
    }
  };

  const handleDeleteAccount = () => {
    if (!confirm('确定要删除账户？此操作不可逆！所有记忆数据将被永久删除。')) return;
    alert('MVP 版本暂不支持删除账户功能');
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
      <h1 className="mb-6 text-2xl font-bold text-slate-100">身份管理</h1>

      {/* Passport ID card */}
      <div className="mb-6 rounded-2xl border border-blue-500/20 bg-gradient-to-br from-slate-800 to-blue-900/20 p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="mb-1 text-xs uppercase text-blue-400/70">Memory Passport ID</p>
            <div className="flex items-center gap-2">
              <Fingerprint className="h-5 w-5 text-blue-400" />
              <span className="font-mono text-xl font-bold text-blue-300">
                {user.passport_id}
              </span>
              <button
                onClick={copyPassportId}
                className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-blue-400"
              >
                {copied ? (
                  <CheckCircle className="h-4 w-4 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
          <div className="rounded-xl bg-slate-700/50 px-3 py-1 text-xs text-slate-400">
            创建于 {formatDate(user.created_at)}
          </div>
        </div>
      </div>

      {/* Profile */}
      <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-200">
          <Mail className="h-5 w-5 text-slate-400" /> 个人信息
        </h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-slate-400">邮箱</label>
            <p className="text-slate-300">{user.email}</p>
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-400">显示名称</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="flex-1 rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={handleUpdateProfile}
                disabled={saving || displayName === user.display_name}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Wallet binding (reserved) */}
      <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-200">
          <Wallet className="h-5 w-5 text-slate-400" /> 钱包绑定
        </h2>
        {user.wallet_address ? (
          <p className="font-mono text-sm text-green-400">{user.wallet_address}</p>
        ) : (
          <div className="rounded-lg bg-slate-700/30 p-4 text-center">
            <p className="text-sm text-slate-500">钱包绑定功能将在后续版本开放</p>
            <p className="mt-1 text-xs text-slate-600">
              支持 Ethereum 钱包签名验证 (SIWE)
            </p>
          </div>
        )}
      </section>

      {/* Privacy & Data */}
      <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
        <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-200">
          <Shield className="h-5 w-5 text-slate-400" /> 隐私与数据
        </h2>
        <div className="space-y-3">
          <button
            onClick={handleExportAll}
            className="flex w-full items-center gap-2 rounded-lg border border-slate-600 px-4 py-3 text-sm text-slate-300 transition-colors hover:bg-slate-700"
          >
            <Download className="h-4 w-4" />
            导出全部数据 (JSON)
          </button>
          <button
            onClick={handleDeleteAccount}
            className="flex w-full items-center gap-2 rounded-lg border border-red-500/30 px-4 py-3 text-sm text-red-400 transition-colors hover:bg-red-900/20"
          >
            <Trash2 className="h-4 w-4" />
            删除账户及所有数据
          </button>
        </div>
      </section>
    </div>
  );
}

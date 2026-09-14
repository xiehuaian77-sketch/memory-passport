'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Bot,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Key,
  Copy,
  Check,
  AlertTriangle,
  History,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import * as api from '@/lib/api';
import type {
  Agent,
  AgentPermissionType,
  PermissionGrant,
  AgentAuditLog,
} from '@/types';
import { formatDate } from '@/lib/utils';

interface AgentAccessControlProps {
  token: string;
}

const CANONICAL_PERMISSIONS: {
  key: AgentPermissionType;
  label: string;
  desc: string;
}[] = [
  {
    key: 'READ_MEMORY',
    label: 'READ_MEMORY',
    desc: '读取全部记忆（语义检索、关键词、上下文装配及资源）',
  },
  {
    key: 'READ_PREFERENCES',
    label: 'READ_PREFERENCES',
    desc: '仅偏好读取（服务端安全过滤，仅限用户偏好记忆）',
  },
  {
    key: 'CREATE_MEMORY',
    label: 'CREATE_MEMORY',
    desc: '创建新记忆（允许代表用户写入长程记忆）',
  },
  {
    key: 'UPDATE_MEMORY',
    label: 'UPDATE_MEMORY',
    desc: '更新已有记忆（允许修改用户已有长程记忆）',
  },
];

export default function AgentAccessControl({ token }: AgentAccessControlProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [permissionsMap, setPermissionsMap] = useState<Record<string, PermissionGrant[]>>({});
  const [auditLogs, setAuditLogs] = useState<AgentAuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [creating, setCreating] = useState(false);

  // One-time Key Display State (strictly in-memory, never persisted to localStorage)
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [keyCopied, setKeyCopied] = useState(false);

  // Revoke & Action confirmation states
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchAgentsAndGrants = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const agentList = await api.listAgents(token);
      setAgents(agentList);

      const grantsObj: Record<string, PermissionGrant[]> = {};
      await Promise.all(
        agentList.map(async (ag) => {
          try {
            const grants = await api.listAgentPermissions(token, ag.id);
            grantsObj[ag.id] = grants;
          } catch {
            grantsObj[ag.id] = [];
          }
        })
      );
      setPermissionsMap(grantsObj);

      try {
        const logs = await api.listAgentAuditLogs(token);
        setAuditLogs(logs);
      } catch {
        setAuditLogs([]);
      }
    } catch (err: any) {
      setError(err?.message || '加载 Agent 列表失败');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchAgentsAndGrants();
  }, [fetchAgentsAndGrants]);

  const handleCreateAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const res = await api.createAgent(token, {
        name: createName.trim(),
        description: createDesc.trim() || undefined,
      });
      setNewlyCreatedKey(res.api_key);
      setShowCreateModal(false);
      setCreateName('');
      setCreateDesc('');
      await fetchAgentsAndGrants();
    } catch (err: any) {
      setError(err?.message || '创建 Agent 失败');
    } finally {
      setCreating(false);
    }
  };

  const handleCopyKey = () => {
    if (!newlyCreatedKey) return;
    navigator.clipboard.writeText(newlyCreatedKey);
    setKeyCopied(true);
    setTimeout(() => setKeyCopied(false), 2000);
  };

  const handleDismissOneTimeKey = () => {
    setNewlyCreatedKey(null);
    setKeyCopied(false);
  };

  const handleRevokeAgent = async (agentId: string, agentName: string) => {
    if (!confirm(`确定要彻底撤销 Agent "${agentName}" 的访问权限吗？撤销后该 Agent 的所有 API Key 和权限将立即失效。`)) {
      return;
    }
    setActionLoading(`revoke_agent_${agentId}`);
    try {
      await api.revokeAgent(token, agentId);
      await fetchAgentsAndGrants();
    } catch (err: any) {
      alert(`撤销 Agent 失败: ${err?.message || err}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleGrantPermission = async (agentId: string, permission: AgentPermissionType) => {
    setActionLoading(`grant_${agentId}_${permission}`);
    try {
      await api.grantAgentPermission(token, agentId, permission);
      await fetchAgentsAndGrants();
    } catch (err: any) {
      alert(`授权失败: ${err?.message || err}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokePermission = async (
    agentId: string,
    permission: AgentPermissionType
  ) => {
    if (!confirm(`确定要撤销此 Agent 的 ${permission} 权限吗？`)) {
      return;
    }
    setActionLoading(`revoke_${agentId}_${permission}`);
    try {
      await api.revokeAgentPermission(token, agentId, permission);
      await fetchAgentsAndGrants();
    } catch (err: any) {
      alert(`撤销权限失败: ${err?.message || err}`);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-200">
            <Bot className="h-5 w-5 text-indigo-400" />
            AI Agent 访问控制 (Agent Access Control)
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            授权与管理外部 AI Agent 对 Memory Passport 的访问权限，遵循最小特权原则与实时撤销机制。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchAgentsAndGrants}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-600 bg-slate-700/50 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50"
            title="刷新状态"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >
            <Plus className="h-3.5 w-3.5" />
            注册新 Agent
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-xs text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading State */}
      {loading && agents.length === 0 ? (
        <div className="py-12 text-center text-sm text-slate-400">
          <RefreshCw className="mx-auto mb-2 h-6 w-6 animate-spin text-slate-500" />
          正在加载 Agent 列表及权限...
        </div>
      ) : agents.length === 0 ? (
        /* Empty State */
        <div className="mt-6 rounded-lg border border-dashed border-slate-700 p-8 text-center">
          <Bot className="mx-auto h-10 w-10 text-slate-600" />
          <p className="mt-2 text-sm font-medium text-slate-300">尚未注册任何 AI Agent</p>
          <p className="mt-1 text-xs text-slate-500">
            点击上方 &quot;注册新 Agent&quot; 按钮生成独立 API Key，并为其按需分配只读或写入权限。
          </p>
        </div>
      ) : (
        /* Agent Cards List */
        <div className="mt-6 space-y-5">
          {agents.map((ag) => {
            const grants = permissionsMap[ag.id] || [];
            const isRevoked = ag.status === 'revoked';

            return (
              <div
                key={ag.id}
                className={`rounded-xl border p-5 transition-colors ${
                  isRevoked
                    ? 'border-slate-800 bg-slate-900/40 opacity-75'
                    : 'border-slate-700 bg-slate-800/60'
                }`}
              >
                {/* Agent Header */}
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                        isRevoked
                          ? 'bg-slate-800 text-slate-500'
                          : 'bg-indigo-950 text-indigo-400 border border-indigo-800/50'
                      }`}
                    >
                      <Bot className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-200">{ag.name}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${
                            isRevoked
                              ? 'bg-red-950/60 text-red-400 border border-red-800/40'
                              : 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/40'
                          }`}
                        >
                          {ag.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400">
                        {ag.description || '无附加描述'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-end sm:self-auto">
                    <div className="text-right text-[11px] text-slate-500">
                      <div>注册于 {formatDate(ag.created_at)}</div>
                      <div className="font-mono text-[10px] text-slate-600">ID: {ag.id.slice(0, 8)}...</div>
                    </div>
                    {!isRevoked && (
                      <button
                        onClick={() => handleRevokeAgent(ag.id, ag.name)}
                        disabled={actionLoading === `revoke_agent_${ag.id}`}
                        className="rounded-lg border border-red-800/60 bg-red-950/30 px-2.5 py-1 text-xs text-red-400 hover:bg-red-900/50 disabled:opacity-50"
                      >
                        {actionLoading === `revoke_agent_${ag.id}` ? '撤销中...' : '撤销 Agent'}
                      </button>
                    )}
                  </div>
                </div>

                {/* Permissions Matrix */}
                <div className="mt-4 border-t border-slate-700/60 pt-4">
                  <div className="mb-2.5 flex items-center justify-between">
                    <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                      授权权限 (Permission Delegations)
                    </span>
                    {isRevoked && (
                      <span className="text-xs text-red-400/90 font-medium">
                        Agent 已撤销，所有权限已被强制冻结
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    {CANONICAL_PERMISSIONS.map((perm) => {
                      const activeGrant = grants.find(
                        (g) => g.permission === perm.key && g.is_active
                      );
                      const isGranted = Boolean(activeGrant);
                      const isLoadingAction =
                        actionLoading === `grant_${ag.id}_${perm.key}` ||
                        actionLoading === `revoke_${ag.id}_${perm.key}`;

                      return (
                        <div
                          key={perm.key}
                          className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-900/30 p-3"
                        >
                          <div className="min-w-0 flex-1 pr-2">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs font-semibold text-slate-200">
                                {perm.label}
                              </span>
                              {isGranted ? (
                                <span className="flex items-center gap-1 rounded bg-emerald-950/80 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400 border border-emerald-800/50">
                                  <ShieldCheck className="h-3 w-3" /> 已授权
                                </span>
                              ) : (
                                <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                                  未授权
                                </span>
                              )}
                            </div>
                            <p className="mt-1 line-clamp-1 text-[11px] text-slate-400">
                              {perm.desc}
                            </p>
                          </div>

                          <div>
                            {isGranted ? (
                              <button
                                onClick={() => handleRevokePermission(ag.id, perm.key)}
                                disabled={isRevoked || isLoadingAction}
                                className="rounded border border-amber-800/40 bg-amber-950/30 px-2 py-1 text-xs text-amber-400 hover:bg-amber-900/40 disabled:opacity-40"
                              >
                                {isLoadingAction ? '...' : '撤销'}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleGrantPermission(ag.id, perm.key)}
                                disabled={isRevoked || isLoadingAction}
                                className="rounded border border-indigo-700/50 bg-indigo-950/40 px-2 py-1 text-xs text-indigo-300 hover:bg-indigo-900/50 disabled:opacity-40"
                              >
                                {isLoadingAction ? '...' : '授权'}
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Audit Log Section */}
      <div className="mt-8 border-t border-slate-700 pt-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
            <History className="h-4 w-4 text-indigo-400" />
            Agent 访问与权限审计记录 (Audit Logs)
          </div>
          <span className="text-[11px] text-slate-500">
            共 {auditLogs.length} 条记录 (零敏感凭据保证)
          </span>
        </div>

        {auditLogs.length === 0 ? (
          <p className="text-xs text-slate-500 py-3">暂无 Agent 访问审计记录</p>
        ) : (
          <div className="max-h-60 overflow-y-auto space-y-2 pr-1 text-xs">
            {auditLogs.slice(0, 15).map((log) => {
              const isAllow = log.decision === 'ALLOW';
              const isDeny = log.decision === 'DENY';

              return (
                <div
                  key={log.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between rounded-lg border border-slate-700/40 bg-slate-900/40 p-2.5 gap-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-slate-500">
                      {formatDate(log.created_at)}
                    </span>
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                      {log.action}
                    </span>
                    {log.tool && (
                      <span className="font-mono text-[11px] text-indigo-300">
                        {log.tool}
                      </span>
                    )}
                    {log.permission && (
                      <span className="font-mono text-[10px] text-slate-400">
                        [{log.permission}]
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {isAllow && (
                      <span className="flex items-center gap-1 text-emerald-400 font-semibold text-[11px]">
                        <CheckCircle2 className="h-3 w-3" /> ALLOW
                      </span>
                    )}
                    {isDeny && (
                      <span className="flex items-center gap-1 text-rose-400 font-semibold text-[11px]">
                        <XCircle className="h-3 w-3" /> DENY
                      </span>
                    )}
                    {log.reason && (
                      <span className="text-slate-400 text-[11px] truncate max-w-xs" title={log.reason}>
                        {log.reason}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal: Create Agent */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
            <h3 className="flex items-center gap-2 text-base font-semibold text-slate-200">
              <Key className="h-5 w-5 text-indigo-400" />
              注册新 AI Agent
            </h3>
            <p className="mt-1 text-xs text-slate-400">
              系统将为此 Agent 签发专属 API Key。创建完成后请立即复制保存。
            </p>

            <form onSubmit={handleCreateAgent} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300">
                  Agent 名称 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  maxLength={100}
                  placeholder="例如: Claude Assistant, AutoResearcher"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300">
                  描述用途 (可选)
                </label>
                <textarea
                  rows={3}
                  maxLength={1000}
                  placeholder="说明该 Agent 的职责、使用场景及授权范围..."
                  value={createDesc}
                  onChange={(e) => setCreateDesc(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                  className="rounded-lg border border-slate-600 bg-slate-700/50 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={creating || !createName.trim()}
                  className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {creating ? '生成密钥中...' : '确认创建'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: One-Time Key Display (Crucial Security UX) */}
      {newlyCreatedKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="w-full max-w-lg rounded-xl border border-amber-600/60 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-center gap-2.5 text-amber-400">
              <ShieldAlert className="h-6 w-6 shrink-0" />
              <h3 className="text-base font-bold text-slate-100">
                请立即妥善保存 Agent API Key
              </h3>
            </div>

            <div className="mt-3 rounded-lg border border-amber-900/60 bg-amber-950/30 p-3.5 text-xs text-amber-200/90 leading-relaxed">
              <p className="font-semibold text-amber-300 mb-1">
                ⚠️ 该密钥仅在当前窗口显示一次：
              </p>
              出于零信任安全要求，系统数据库仅保存此密钥的加盐哈希值。一旦关闭该窗口或刷新页面，原始密钥将无法再次恢复或查看。请将其安全配置在你的 MCP Agent Client 中。
            </div>

            <div className="mt-4">
              <label className="block text-xs font-medium text-slate-300 mb-1">
                API Key (Bearer Token):
              </label>
              <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 p-3">
                <code className="flex-1 font-mono text-xs text-emerald-400 break-all select-all">
                  {newlyCreatedKey}
                </code>
                <button
                  onClick={handleCopyKey}
                  className="flex shrink-0 items-center gap-1 rounded bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
                >
                  {keyCopied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-300" /> 已复制
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" /> 复制 Key
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={handleDismissOneTimeKey}
                className="rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white hover:bg-emerald-500"
              >
                我已妥善保存 (I&apos;ve Saved It)
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

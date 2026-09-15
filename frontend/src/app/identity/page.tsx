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
  AlertCircle,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import * as api from '@/lib/api';
import { formatDate } from '@/lib/utils';
import * as web3 from '@/lib/web3';
import AgentAccessControl from '@/components/AgentAccessControl';

export default function IdentityPage() {
  const { user, token, isLoading, logout, refreshUser } = useAuth();
  const router = useRouter();
  const [copied, setCopied] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [saving, setSaving] = useState(false);

  // Web3 state
  const [connectedAddress, setConnectedAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [walletConnecting, setWalletConnecting] = useState(false);
  const [walletVerifying, setWalletVerifying] = useState(false);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletSuccess, setWalletSuccess] = useState<string | null>(null);
  const [addressCopied, setAddressCopied] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
      return;
    }
    if (user) setDisplayName(user.display_name);
  }, [isLoading, user, router]);

  // Read initial wallet connection & subscribe to events (read-only, no auto-popup)
  useEffect(() => {
    let unmounted = false;

    async function initWeb3() {
      const addr = await web3.getConnectedAddress();
      const cid = await web3.getChainId();
      if (!unmounted) {
        if (addr) setConnectedAddress(addr);
        if (cid !== null) setChainId(cid);
      }
    }

    initWeb3();

    const unsubAccounts = web3.onAccountsChanged((accounts) => {
      setConnectedAddress(accounts.length > 0 ? accounts[0] : null);
      setWalletError(null);
    });

    const unsubChain = web3.onChainChanged((cidHex) => {
      const parsed = typeof cidHex === 'string' ? parseInt(cidHex, 16) : Number(cidHex);
      setChainId(parsed);
      setWalletError(null);
    });

    return () => {
      unmounted = true;
      unsubAccounts();
      unsubChain();
    };
  }, []);

  const copyPassportId = () => {
    if (!user) return;
    navigator.clipboard.writeText(user.passport_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyWalletAddress = (address: string) => {
    navigator.clipboard.writeText(address);
    setAddressCopied(true);
    setTimeout(() => setAddressCopied(false), 2000);
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
    if (confirm('确定要删除账户吗？所有记忆数据将被永久清除。此操作不可恢复。')) {
      logout();
      router.push('/');
    }
  };

  // Web3 Handlers
  const handleConnectWallet = async () => {
    setWalletError(null);
    setWalletSuccess(null);
    setWalletConnecting(true);
    try {
      const address = await web3.connectWallet();
      setConnectedAddress(address);
      const cid = await web3.getChainId();
      setChainId(cid);
    } catch (err: any) {
      setWalletError(err.message || '连接钱包失败');
    } finally {
      setWalletConnecting(false);
    }
  };

  const handleSwitchNetwork = async () => {
    setWalletError(null);
    try {
      await web3.switchToMonadTestnet();
      const cid = await web3.getChainId();
      setChainId(cid);
    } catch (err: any) {
      setWalletError(err.message || '网络切换失败');
    }
  };

  const handleVerifyWallet = async () => {
    if (!connectedAddress) {
      setWalletError('请先连接钱包');
      return;
    }
    setWalletError(null);
    setWalletSuccess(null);
    setWalletVerifying(true);

    try {
      // 1. Ensure Monad Testnet before signing
      if (chainId !== web3.MONAD_CHAIN_ID_DECIMAL) {
        await web3.switchToMonadTestnet();
        const newCid = await web3.getChainId();
        setChainId(newCid);
      }

      // 2. Request backend challenge nonce
      const nonceData = await api.getWalletNonce(connectedAddress, web3.MONAD_CHAIN_ID_DECIMAL);

      // 3. User signs the exact server-provided SIWE message
      const signature = await web3.signMessage(nonceData.message, connectedAddress);

      // 4. Verify signature on backend with existing user session
      await api.verifyWallet(
        {
          address: connectedAddress,
          signature,
          nonce: nonceData.nonce,
        },
        token
      );

      // 5. Refresh user state from /api/auth/me
      await refreshUser();
      setWalletSuccess('钱包所有权验证成功！已绑定至当前 Memory Passport。');
    } catch (err: any) {
      setWalletError(err.message || '签名验证失败');
    } finally {
      setWalletVerifying(false);
    }
  };

  if (isLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  const isMonadChain = chainId === web3.MONAD_CHAIN_ID_DECIMAL;
  const isBound = !!user.wallet_address;

  return (
    <div className="min-h-screen bg-slate-900 px-4 py-8 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">身份与凭证中心</h1>
            <p className="mt-1 text-sm text-slate-400">
              管理你的 Memory Passport 主权数字身份、Web3 钱包归属与数据资产
            </p>
          </div>
          <button
            onClick={() => router.push('/dashboard')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-700"
          >
            返回控制台
          </button>
        </div>

        {/* Passport Card */}
        <div className="mb-8 overflow-hidden rounded-2xl border border-blue-500/30 bg-gradient-to-br from-blue-900/40 via-slate-800 to-purple-900/30 p-6 shadow-xl backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600/30 border border-blue-400/40 text-blue-400">
                <Fingerprint className="h-7 w-7" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white">{user.display_name}</h2>
                <p className="text-sm text-slate-400">{user.email}</p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-green-500/30 bg-green-500/10 px-3 py-1 text-xs font-medium text-green-400">
              <CheckCircle className="h-3.5 w-3.5" />
              已验证护照
            </span>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                Passport ID (唯一护照标识)
              </span>
              <div className="mt-1 flex items-center justify-between">
                <code className="font-mono text-base font-semibold text-blue-400">
                  {user.passport_id}
                </code>
                <button
                  onClick={copyPassportId}
                  className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
                  title="复制 Passport ID"
                >
                  {copied ? <CheckCircle className="h-4 w-4 text-green-400" /> : <Copy className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
              <span className="text-xs font-medium uppercase tracking-wider text-slate-400">
                创建时间
              </span>
              <p className="mt-1 text-base font-medium text-slate-200">
                {formatDate(user.created_at)}
              </p>
            </div>
          </div>
        </div>

        {/* Web3 Sovereign Identity & Wallet Binding Section */}
        <section className="mb-6 rounded-xl border border-purple-500/30 bg-slate-800/50 p-6 shadow-md">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Wallet className="h-5 w-5 text-purple-400" />
              <h2 className="text-lg font-semibold text-white">Web3 主权身份 (Sovereign Ownership)</h2>
            </div>
            {isBound && (
              <span className="inline-flex items-center gap-1 rounded-full border border-purple-400/40 bg-purple-500/10 px-2.5 py-0.5 text-xs font-medium text-purple-300">
                <CheckCircle className="h-3.5 w-3.5 text-purple-400" />
                所有权已锚定
              </span>
            )}
          </div>
          <p className="mb-4 text-sm text-slate-400">
            连接 Monad / EVM 钱包并完成密码学签名验证，确立对 Memory Passport 长程记忆资产的不可篡改主权。
          </p>

          {/* Feedback alerts */}
          {walletError && (
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
              <AlertCircle className="h-4 w-4 flex-shrink-0 text-red-400" />
              <span>{walletError}</span>
            </div>
          )}
          {walletSuccess && (
            <div className="mb-4 flex items-center gap-2 rounded-lg border border-green-500/40 bg-green-500/10 p-3 text-sm text-green-300">
              <CheckCircle className="h-4 w-4 flex-shrink-0 text-green-400" />
              <span>{walletSuccess}</span>
            </div>
          )}

          {/* Status D & E: User has verified bound wallet */}
          {isBound ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-green-500/30 bg-green-950/20 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-700/60 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-green-400 animate-pulse" />
                    <span className="text-sm font-semibold text-green-300">
                      ✓ Sovereign Wallet Bound (主权归属已确立)
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-purple-900/50 border border-purple-500/30 px-2 py-0.5 text-xs font-mono text-purple-300">
                      Monad Testnet (10143)
                    </span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <span className="text-xs text-slate-400">已绑定钱包地址</span>
                    <div className="mt-1 flex items-center gap-2">
                      <code className="font-mono text-sm font-semibold text-green-400">
                        {web3.formatAddress(user.wallet_address)}
                      </code>
                      <button
                        onClick={() => copyWalletAddress(user.wallet_address!)}
                        className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
                        title="复制完整钱包地址"
                      >
                        {addressCopied ? (
                          <CheckCircle className="h-3.5 w-3.5 text-green-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <a
                        href={`${web3.MONAD_EXPLORER_URL}/address/${user.wallet_address}`}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded p-1 text-slate-400 hover:text-purple-300"
                        title="在 Monad 浏览器中查看"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </div>

                  <div>
                    <span className="text-xs text-slate-400">主权认证时间戳</span>
                    <p className="mt-1 text-sm font-medium text-slate-300">
                      {user.wallet_bound_at ? formatDate(user.wallet_bound_at) : '已完成密码学认证'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Browser wallet status & network switch helper */}
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-800/40 p-3 text-xs text-slate-300">
                <div className="flex items-center gap-2">
                  <span>当前浏览器钱包:</span>
                  <code className="font-mono text-slate-200">
                    {connectedAddress ? web3.formatAddress(connectedAddress) : '未连接'}
                  </code>
                  {connectedAddress && (
                    <span
                      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${
                        isMonadChain
                          ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      }`}
                    >
                      {isMonadChain ? 'Monad Testnet' : `Chain: ${chainId ?? 'Unknown'}`}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {connectedAddress && !isMonadChain && (
                    <button
                      onClick={handleSwitchNetwork}
                      className="rounded bg-purple-600/80 px-2.5 py-1 text-xs font-medium text-white hover:bg-purple-600"
                    >
                      切换至 Monad Testnet
                    </button>
                  )}
                  {!connectedAddress && (
                    <button
                      onClick={handleConnectWallet}
                      disabled={walletConnecting}
                      className="rounded border border-slate-600 bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-slate-600"
                    >
                      {walletConnecting ? '连接中...' : '连接当前钱包'}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            /* States A, B, C: Wallet not yet bound */
            <div className="space-y-4">
              {!connectedAddress ? (
                /* State A: No wallet connected */
                <div className="rounded-xl border border-dashed border-slate-700 bg-slate-800/30 p-6 text-center">
                  <Wallet className="mx-auto h-10 w-10 text-slate-500" />
                  <h3 className="mt-3 text-base font-semibold text-slate-200">尚未连接 Web3 钱包</h3>
                  <p className="mx-auto mt-1 max-w-md text-xs text-slate-400">
                    请连接你的 MetaMask、Rabby 或 OKX 钱包以确立对此 Passport 记忆数据的密码学主权持有。
                  </p>
                  <div className="mt-5">
                    <button
                      onClick={handleConnectWallet}
                      disabled={walletConnecting}
                      className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-900/30 hover:bg-purple-500 disabled:opacity-50"
                    >
                      {walletConnecting ? (
                        <>
                          <RefreshCw className="h-4 w-4 animate-spin" />
                          正在连接钱包...
                        </>
                      ) : (
                        <>
                          <Wallet className="h-4 w-4" />
                          Connect Monad / EVM Wallet
                        </>
                      )}
                    </button>
                  </div>
                </div>
              ) : (
                /* State B & C: Wallet connected, ready to verify ownership */
                <div className="rounded-xl border border-purple-500/40 bg-purple-950/20 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700/60 pb-3">
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-blue-400" />
                      <span className="text-sm font-semibold text-slate-200">检测到浏览器钱包:</span>
                      <code className="font-mono text-sm font-bold text-purple-300">
                        {web3.formatAddress(connectedAddress)}
                      </code>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-mono font-medium ${
                          isMonadChain
                            ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                            : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                        }`}
                      >
                        {isMonadChain ? 'Monad Testnet (10143)' : `网络异常 (Chain: ${chainId ?? 'Unknown'})`}
                      </span>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
                    <p className="text-xs text-slate-400 max-w-md">
                      点击下方按钮，钱包将弹出 EIP-4361 (SIWE) 真实消息签名请求。完成签名后，此钱包地址将被绑定为该护照的唯一主权所有者。
                    </p>

                    <div className="flex items-center gap-2">
                      {!isMonadChain && (
                        <button
                          onClick={handleSwitchNetwork}
                          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-300 hover:bg-amber-500/20"
                        >
                          Switch to Monad Testnet
                        </button>
                      )}
                      <button
                        onClick={handleVerifyWallet}
                        disabled={walletVerifying}
                        className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-500 disabled:opacity-50"
                      >
                        {walletVerifying ? (
                          <>
                            <RefreshCw className="h-4 w-4 animate-spin" />
                            Waiting for wallet signature...
                          </>
                        ) : (
                          <>
                            <Shield className="h-4 w-4" />
                            Verify Wallet Ownership
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* AI Agent Access Control & Permission Delegation Section */}
        {token && <AgentAccessControl token={token} />}

        {/* Profile Edit */}
        <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-200">
            <Mail className="h-5 w-5 text-slate-400" /> 基本信息
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-slate-400">
                注册邮箱
              </label>
              <p className="mt-1 text-sm text-slate-300">{user.email}</p>
            </div>
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-slate-400">
                显示名称
              </label>
              <div className="mt-1 flex gap-3">
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

        {/* Privacy & Data */}
        <section className="mb-6 rounded-xl border border-slate-700 bg-slate-800/50 p-6">
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-200">
            <Shield className="h-5 w-5 text-slate-400" /> 隐私与数据
          </h2>
          <div className="space-y-3">
            <button
              onClick={handleExportAll}
              className="flex w-full items-center justify-between rounded-lg border border-slate-700 bg-slate-700/30 p-3 text-sm text-slate-200 hover:bg-slate-700/60"
            >
              <span className="flex items-center gap-2">
                <Download className="h-4 w-4 text-slate-400" />
                导出所有记忆数据 (JSON)
              </span>
              <span className="text-xs text-slate-500">符合 GDPR / 可便携</span>
            </button>
          </div>
        </section>

        {/* Danger Zone */}
        <section className="rounded-xl border border-red-900/30 bg-red-950/10 p-6">
          <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold text-red-400">
            <Trash2 className="h-5 w-5" /> 危险区域
          </h2>
          <p className="mb-4 text-xs text-slate-400">
            删除账户将永久清除你的 Passport 记录及关联的全部长程记忆、图谱和评测数据。
          </p>
          <button
            onClick={handleDeleteAccount}
            className="rounded-lg border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-400 hover:bg-red-900/60"
          >
            删除账户及所有数据
          </button>
        </section>
      </div>
    </div>
  );
}

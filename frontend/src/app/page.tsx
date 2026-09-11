'use client';

import Link from 'next/link';
import {
  Brain,
  ArrowRight,
  Fingerprint,
  Shield,
  Clock,
  CheckCircle,
  Plug,
  MoveRight,
} from 'lucide-react';

const FEATURES = [
  {
    icon: MoveRight,
    title: '可迁移',
    desc: '记忆不锁死在单个应用，跨 AI 工具自由流转',
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
  },
  {
    icon: Shield,
    title: '可控制',
    desc: '用户决定哪些记忆可共享，完全掌控数据所有权',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
  },
  {
    icon: Clock,
    title: '可追溯',
    desc: '每条记忆标注来源、时间和可信度，清晰透明',
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
  },
  {
    icon: CheckCircle,
    title: '可验证',
    desc: '区分高可信和低可信记忆，AI 推断有据可依',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
  },
  {
    icon: Plug,
    title: '可扩展',
    desc: 'MCP 标准协议接口，接入更多 AI 工具和 Agent',
    color: 'text-orange-400',
    bg: 'bg-orange-500/10',
  },
  {
    icon: Fingerprint,
    title: '身份层',
    desc: '为每个用户创建唯一 Passport ID，构建 AI 身份基础设施',
    color: 'text-pink-400',
    bg: 'bg-pink-500/10',
  },
];

const STEPS = [
  { num: '01', title: '创建 Passport', desc: '注册并获得唯一记忆身份标识' },
  { num: '02', title: '录入记忆', desc: '保存偏好、身份、任务等信息' },
  { num: '03', title: '对话验证', desc: 'AI 自动加载记忆，个性化回答' },
  { num: '04', title: '跨应用迁移', desc: '不同 AI 共享同一份记忆上下文' },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="relative overflow-hidden px-4 py-24 text-center">
        <div className="absolute inset-0 bg-gradient-to-b from-blue-600/5 via-purple-600/5 to-transparent" />
        <div className="relative mx-auto max-w-4xl">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-800/50 px-4 py-1.5 text-sm text-slate-400">
            <Brain className="h-4 w-4 text-blue-400" />
            <span>AI 记忆基础设施</span>
          </div>
          <h1 className="mb-6 text-5xl font-extrabold leading-tight md:text-6xl">
            <span className="gradient-text">Memory Passport</span>
          </h1>
          <p className="mx-auto mb-8 max-w-2xl text-lg text-slate-400 md:text-xl">
            让 AI 真正记住你。一个可迁移、可控制、可追溯的记忆身份层，
            在不同 AI 应用之间保持上下文连续。
          </p>
          <div className="flex justify-center gap-4">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-6 py-3 font-semibold text-white shadow-lg shadow-blue-600/20 transition-all hover:bg-blue-500 hover:shadow-blue-600/30"
            >
              开始使用
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 px-6 py-3 font-semibold text-slate-300 transition-colors hover:bg-slate-800"
            >
              查看记忆面板
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="mb-12 text-center text-3xl font-bold text-slate-100">
          核心特性
        </h2>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="card-glow rounded-2xl border border-slate-700 bg-slate-800/50 p-6 transition-transform hover:scale-[1.02]"
              >
                <div
                  className={`mb-4 inline-flex rounded-xl ${f.bg} p-3`}
                >
                  <Icon className={`h-6 w-6 ${f.color}`} />
                </div>
                <h3 className="mb-2 text-lg font-bold text-slate-100">{f.title}</h3>
                <p className="text-sm text-slate-400">{f.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-4xl px-4 py-16">
        <h2 className="mb-12 text-center text-3xl font-bold text-slate-100">
          工作流程
        </h2>
        <div className="grid gap-6 md:grid-cols-2">
          {STEPS.map((s) => (
            <div
              key={s.num}
              className="flex gap-4 rounded-xl border border-slate-700 bg-slate-800/30 p-5"
            >
              <span className="text-3xl font-extrabold text-blue-500/30">
                {s.num}
              </span>
              <div>
                <h3 className="mb-1 font-bold text-slate-200">{s.title}</h3>
                <p className="text-sm text-slate-400">{s.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-8 text-center text-sm text-slate-600">
        Memory Passport v0.1.0 — Built for Hackathon 2026
      </footer>
    </div>
  );
}

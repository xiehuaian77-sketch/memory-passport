'use client';

import { useState, useEffect } from 'react';
import {
  Inbox,
  Check,
  X,
  Edit3,
  AlertTriangle,
  Quote,
  Sparkles,
  ShieldCheck,
  Save,
  Loader2,
} from 'lucide-react';
import type { ConversationMemoryCandidate, ConflictItem } from '@/types';
import { CATEGORY_COLORS, CATEGORY_LABELS, MemoryCategory } from '@/types';
import { cn } from '@/lib/utils';
import * as api from '@/lib/api';

interface MemoryInboxProps {
  candidates: ConversationMemoryCandidate[];
  token: string;
  onConfirm: (cand: ConversationMemoryCandidate) => Promise<void>;
  onEditAndConfirm: (
    cand: ConversationMemoryCandidate,
    editedContent: string,
    editedKey: string
  ) => Promise<void>;
  onDismiss: (candidateId: string) => void;
}

export default function MemoryInbox({
  candidates,
  token,
  onConfirm,
  onEditAndConfirm,
  onDismiss,
}: MemoryInboxProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editKey, setEditKey] = useState('');
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [conflictsMap, setConflictsMap] = useState<Record<string, ConflictItem[]>>({});

  // Check conflicts asynchronously for incoming candidates
  useEffect(() => {
    let isMounted = true;
    candidates.forEach(async (cand) => {
      try {
        const res = await api.detectConflicts(token, {
          key: cand.key,
          content: cand.content,
          memory_type: cand.memory_type,
        });
        if (isMounted) {
          setConflictsMap((prev) => ({
            ...prev,
            [cand.id]: res.has_conflict ? res.conflicts : [],
          }));
        }
      } catch {
        // Conflict check failure should not block user workflow
      }
    });
    return () => {
      isMounted = false;
    };
  }, [candidates, token]);

  const handleStartEdit = (cand: ConversationMemoryCandidate) => {
    setEditingId(cand.id);
    setEditContent(cand.content);
    setEditKey(cand.key);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditContent('');
    setEditKey('');
  };

  const handleSaveEdit = async (cand: ConversationMemoryCandidate) => {
    if (!editContent.trim()) return;
    try {
      setProcessingId(cand.id);
      await onEditAndConfirm(cand, editContent.trim(), editKey.trim() || cand.key);
      setEditingId(null);
    } finally {
      setProcessingId(null);
    }
  };

  const handleDirectConfirm = async (cand: ConversationMemoryCandidate) => {
    try {
      setProcessingId(cand.id);
      await onConfirm(cand);
    } finally {
      setProcessingId(null);
    }
  };

  if (candidates.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-800/20 py-16 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 text-slate-500">
          <Inbox className="h-6 w-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-300">收件箱暂无待确认候选</h3>
        <p className="mt-1 max-w-sm text-xs text-slate-500">
          在「AI 对话」中畅聊，并点击「发现对话记忆」，AI 提取的长期事实与偏好将在此处等待你的授权确认。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
            AI 提炼候选记忆 ({candidates.length})
          </h2>
        </div>
        <span className="text-xs text-slate-500">
          严格防篡改验证 · 仅在经你批准后永久沉淀为长期记忆
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {candidates.map((cand) => {
          const cat = cand.memory_type as MemoryCategory;
          const isProcessing = processingId === cand.id;
          const isEditing = editingId === cand.id;
          const conflicts = conflictsMap[cand.id] || [];

          return (
            <div
              key={cand.id}
              className="flex flex-col justify-between rounded-xl border border-cyan-500/30 bg-slate-800/60 p-4 shadow-lg transition-all animate-fade-in"
            >
              <div>
                {/* Header info */}
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        'rounded-full border px-2 py-0.5 text-xs font-medium',
                        CATEGORY_COLORS[cat] || 'bg-slate-500/20 text-slate-300'
                      )}
                    >
                      {CATEGORY_LABELS[cat] || cat}
                    </span>
                    {!isEditing ? (
                      <span className="text-sm font-semibold text-slate-200">
                        {cand.key}
                      </span>
                    ) : (
                      <input
                        type="text"
                        value={editKey}
                        onChange={(e) => setEditKey(e.target.value)}
                        placeholder="键名"
                        className="rounded border border-slate-600 bg-slate-700 px-2 py-0.5 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
                      />
                    )}
                  </div>
                  <span className="flex items-center gap-1 rounded bg-cyan-950/60 border border-cyan-500/30 px-2 py-0.5 text-[11px] font-medium text-cyan-300">
                    <ShieldCheck className="h-3 w-3" />
                    置信度 {(cand.confidence * 100).toFixed(0)}%
                  </span>
                </div>

                {/* Content body */}
                {!isEditing ? (
                  <p className="text-sm text-slate-200 whitespace-pre-wrap mb-3">
                    {cand.content}
                  </p>
                ) : (
                  <div className="mb-3 space-y-1">
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={3}
                      className="w-full rounded-lg border border-slate-600 bg-slate-700 p-2 text-sm text-slate-200 focus:border-cyan-500 focus:outline-none"
                    />
                    <span className="text-[10px] text-slate-400 block">
                      修改后将自动通过安全审计入库并记录变更痕迹
                    </span>
                  </div>
                )}

                {/* Reason & Dialogue Context */}
                <div className="mb-3 space-y-1.5 rounded-lg bg-slate-900/50 p-2.5 text-xs">
                  {cand.reason && (
                    <div className="text-slate-400">
                      <span className="text-slate-500">提炼原因:</span> {cand.reason}
                    </div>
                  )}
                  {cand.raw_content && (
                    <div className="flex items-start gap-1 text-slate-400 italic">
                      <Quote className="h-3 w-3 shrink-0 text-slate-600 mt-0.5" />
                      <span className="line-clamp-2">&ldquo;{cand.raw_content}&rdquo;</span>
                    </div>
                  )}
                </div>

                {/* Conflict Warning */}
                {conflicts.length > 0 && (
                  <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-950/20 p-2.5 text-xs text-amber-300">
                    <div className="flex items-center gap-1.5 font-semibold">
                      <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                      可能与库内已有记忆冲突 ({conflicts.length})
                    </div>
                    <ul className="mt-1 space-y-1 text-amber-400/80">
                      {conflicts.slice(0, 2).map((c, i) => (
                        <li key={i} className="truncate">
                          · {c.existing_key}: {c.existing_content}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="mt-2 flex items-center justify-end gap-2 border-t border-slate-700/60 pt-3">
                {isEditing ? (
                  <>
                    <button
                      onClick={handleCancelEdit}
                      disabled={isProcessing}
                      className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-700"
                    >
                      取消
                    </button>
                    <button
                      onClick={() => handleSaveEdit(cand)}
                      disabled={isProcessing || !editContent.trim()}
                      className="flex items-center gap-1 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500 disabled:opacity-50"
                    >
                      {isProcessing ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Save className="h-3 w-3" />
                      )}
                      保存修改
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => onDismiss(cand.id)}
                      disabled={isProcessing}
                      className="flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-700 hover:text-red-400 transition-colors"
                      title="忽略此候选，不写入数据库"
                    >
                      <X className="h-3 w-3" />
                      忽略
                    </button>
                    <button
                      onClick={() => handleStartEdit(cand)}
                      disabled={isProcessing}
                      className="flex items-center gap-1 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 hover:text-blue-400 transition-colors"
                      title="编辑内容后再保存"
                    >
                      <Edit3 className="h-3 w-3" />
                      编辑
                    </button>
                    <button
                      onClick={() => handleDirectConfirm(cand)}
                      disabled={isProcessing}
                      className="flex items-center gap-1 rounded-lg bg-cyan-600 px-3.5 py-1.5 text-xs font-medium text-white shadow-md shadow-cyan-600/20 hover:bg-cyan-500 transition-colors disabled:opacity-50"
                    >
                      {isProcessing ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Check className="h-3 w-3" />
                      )}
                      确认保存
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

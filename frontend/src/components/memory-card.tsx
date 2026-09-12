'use client';

import {
  Trash2,
  Edit2,
  Share2,
  ShieldCheck,
  Archive,
  ArchiveRestore,
  Info,
  History,
  MessageSquare,
  AlertTriangle,
} from 'lucide-react';
import type { Memory, MemoryCategory } from '@/types';
import { CATEGORY_COLORS, CATEGORY_LABELS } from '@/types';
import { cn, confidenceColor, confidenceLabel, formatDate } from '@/lib/utils';

interface MemoryCardProps {
  memory: Memory;
  onEdit?: (m: Memory) => void;
  onDelete?: (id: string) => void;
  onToggleShare?: (m: Memory) => void;
  onArchive?: (id: string) => void;
  onRestore?: (id: string) => void;
  onExplain?: (m: Memory) => void;
  onHistory?: (m: Memory) => void;
}

export default function MemoryCard({
  memory,
  onEdit,
  onDelete,
  onToggleShare,
  onArchive,
  onRestore,
  onExplain,
  onHistory,
}: MemoryCardProps) {
  const cat = memory.category as MemoryCategory;
  const isArchived = memory.status === 'archived';
  const isConflicted = memory.status === 'conflicted';
  const isSuperseded = memory.status === 'superseded';

  return (
    <div
      className={cn(
        'card-glow animate-fade-in rounded-xl border p-4 transition-colors',
        isArchived
          ? 'border-slate-800 bg-slate-900/40 opacity-75'
          : isConflicted
          ? 'border-amber-500/30 bg-amber-950/10'
          : isSuperseded
          ? 'border-purple-500/30 bg-purple-950/10'
          : 'border-slate-700 bg-slate-800/50'
      )}
    >
      {/* Header */}
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              'rounded-full border px-2 py-0.5 text-xs font-medium',
              CATEGORY_COLORS[cat] || 'bg-slate-500/20 text-slate-300'
            )}
          >
            {CATEGORY_LABELS[cat] || cat}
          </span>
          <span className="text-sm font-semibold text-slate-200">{memory.key}</span>
          {/* Version badge */}
          <span className="rounded bg-slate-700/60 px-1.5 py-0.2 text-[10px] font-mono text-slate-400">
            v{memory.version || 1}
          </span>
          {/* Status badge */}
          {isArchived && (
            <span className="rounded bg-slate-800 border border-slate-700 px-1.5 py-0.2 text-[10px] font-medium text-slate-400">
              已归档
            </span>
          )}
          {isConflicted && (
            <span className="flex items-center gap-0.5 rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.2 text-[10px] font-medium text-amber-300">
              <AlertTriangle className="h-2.5 w-2.5" /> 冲突预警
            </span>
          )}
          {isSuperseded && (
            <span className="flex items-center gap-0.5 rounded bg-purple-500/20 border border-purple-500/30 px-1.5 py-0.2 text-[10px] font-medium text-purple-300">
              <History className="h-2.5 w-2.5" /> 已更迭
            </span>
          )}
          {(memory.valid_from || memory.valid_until) && (
            <span className="rounded bg-slate-800 border border-slate-700/60 px-1.5 py-0.2 text-[10px] font-mono text-slate-400">
              {memory.valid_from ? formatDate(memory.valid_from) : '起始'} ~ {memory.valid_until ? formatDate(memory.valid_until) : '至今'}
            </span>
          )}
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-1">
          {onExplain && (
            <button
              onClick={() => onExplain(memory)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-cyan-400"
              title="查看可解释性画像"
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          )}
          {onHistory && (
            <button
              onClick={() => onHistory(memory)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-purple-400"
              title="查看审计与变更历史"
            >
              <History className="h-3.5 w-3.5" />
            </button>
          )}
          {onToggleShare && (
            <button
              onClick={() => onToggleShare(memory)}
              className={cn(
                'rounded p-1 transition-colors',
                memory.is_shared
                  ? 'text-blue-400 hover:bg-blue-500/20'
                  : 'text-slate-500 hover:bg-slate-700'
              )}
              title={memory.is_shared ? '已共享' : '未共享'}
            >
              <Share2 className="h-3.5 w-3.5" />
            </button>
          )}
          {onEdit && !isArchived && (
            <button
              onClick={() => onEdit(memory)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-blue-400"
              title="编辑"
            >
              <Edit2 className="h-3.5 w-3.5" />
            </button>
          )}
          {isArchived ? (
            onRestore && (
              <button
                onClick={() => onRestore(memory.id)}
                className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-emerald-400"
                title="恢复至活跃记忆"
              >
                <ArchiveRestore className="h-3.5 w-3.5" />
              </button>
            )
          ) : (
            onArchive && (
              <button
                onClick={() => onArchive(memory.id)}
                className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-amber-400"
                title="归档此记忆"
              >
                <Archive className="h-3.5 w-3.5" />
              </button>
            )
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(memory.id)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400"
              title="永久删除"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <p className="mb-3 text-sm text-slate-300 whitespace-pre-wrap">{memory.content}</p>

      {/* Footer */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <ShieldCheck className="h-3 w-3" />
          <span className={confidenceColor(memory.confidence)}>
            {confidenceLabel(memory.confidence)} ({(memory.confidence * 100).toFixed(0)}%)
          </span>
        </span>
        <span>
          来源:{' '}
          {memory.source === 'manual'
            ? '手动'
            : memory.source === 'ai_extracted'
            ? 'AI提取'
            : '导入'}
        </span>
        {memory.source_conversation_id && (
          <span className="flex items-center gap-0.5 text-blue-400/80">
            <MessageSquare className="h-3 w-3" />
            对话出处
          </span>
        )}
        <span>{formatDate(memory.updated_at)}</span>
      </div>
    </div>
  );
}

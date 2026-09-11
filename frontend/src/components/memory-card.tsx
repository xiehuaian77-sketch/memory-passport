'use client';

import { Trash2, Edit2, Share2, ShieldCheck } from 'lucide-react';
import type { Memory, MemoryCategory } from '@/types';
import { CATEGORY_COLORS, CATEGORY_LABELS } from '@/types';
import { cn, confidenceColor, confidenceLabel, formatDate } from '@/lib/utils';

interface MemoryCardProps {
  memory: Memory;
  onEdit?: (m: Memory) => void;
  onDelete?: (id: string) => void;
  onToggleShare?: (m: Memory) => void;
}

export default function MemoryCard({
  memory,
  onEdit,
  onDelete,
  onToggleShare,
}: MemoryCardProps) {
  const cat = memory.category as MemoryCategory;

  return (
    <div className="card-glow animate-fade-in rounded-xl border border-slate-700 bg-slate-800/50 p-4">
      {/* Header */}
      <div className="mb-2 flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'rounded-full border px-2 py-0.5 text-xs font-medium',
              CATEGORY_COLORS[cat] || 'bg-slate-500/20 text-slate-300'
            )}
          >
            {CATEGORY_LABELS[cat] || cat}
          </span>
          <span className="text-sm font-semibold text-slate-200">{memory.key}</span>
        </div>
        <div className="flex items-center gap-1">
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
          {onEdit && (
            <button
              onClick={() => onEdit(memory)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-blue-400"
            >
              <Edit2 className="h-3.5 w-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(memory.id)}
              className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <p className="mb-3 text-sm text-slate-300">{memory.content}</p>

      {/* Footer */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <ShieldCheck className="h-3 w-3" />
          <span className={confidenceColor(memory.confidence)}>
            {confidenceLabel(memory.confidence)} ({(memory.confidence * 100).toFixed(0)}%)
          </span>
        </span>
        <span>来源: {memory.source === 'manual' ? '手动' : memory.source === 'ai_extracted' ? 'AI提取' : '导入'}</span>
        <span>{formatDate(memory.updated_at)}</span>
      </div>
    </div>
  );
}

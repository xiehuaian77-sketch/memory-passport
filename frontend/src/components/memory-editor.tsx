'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import type { Memory, MemoryCategory } from '@/types';

interface MemoryEditorProps {
  memory?: Memory | null; // null = create mode
  onSave: (data: {
    category: string;
    key: string;
    content: string;
    confidence: number;
    is_shared: boolean;
    tags: string;
  }) => void;
  onClose: () => void;
}

const CATEGORIES: { value: MemoryCategory; label: string }[] = [
  { value: 'preference', label: '偏好' },
  { value: 'identity', label: '身份' },
  { value: 'task', label: '任务' },
  { value: 'context', label: '上下文' },
];

export default function MemoryEditor({ memory, onSave, onClose }: MemoryEditorProps) {
  const [category, setCategory] = useState(memory?.category || 'preference');
  const [key, setKey] = useState(memory?.key || '');
  const [content, setContent] = useState(memory?.content || '');
  const [confidence, setConfidence] = useState(memory?.confidence ?? 1.0);
  const [isShared, setIsShared] = useState(memory?.is_shared ?? true);
  const [tags, setTags] = useState(memory?.tags || '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({ category, key, content, confidence, is_shared: isShared, tags });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="animate-slide-up w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-slate-100">
            {memory ? '编辑记忆' : '添加新记忆'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Category */}
          <div>
            <label className="mb-1 block text-sm text-slate-400">分类</label>
            <div className="flex gap-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setCategory(c.value)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    category === c.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* Key */}
          <div>
            <label className="mb-1 block text-sm text-slate-400">键名</label>
            <input
              type="text"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="如: language_preference"
              required
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Content */}
          <div>
            <label className="mb-1 block text-sm text-slate-400">内容</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="如: 我主要用中文交流"
              required
              rows={3}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Confidence */}
          <div>
            <label className="mb-1 block text-sm text-slate-400">
              可信度: {(confidence * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={confidence}
              onChange={(e) => setConfidence(parseFloat(e.target.value))}
              className="w-full"
            />
          </div>

          {/* Shared */}
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={isShared}
              onChange={(e) => setIsShared(e.target.checked)}
              className="rounded border-slate-600"
            />
            允许外部 AI 读取
          </label>

          {/* Tags */}
          <div>
            <label className="mb-1 block text-sm text-slate-400">标签（逗号分隔）</label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="如: 语言,偏好"
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-slate-700"
            >
              取消
            </button>
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
            >
              {memory ? '保存修改' : '添加记忆'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

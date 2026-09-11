'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import ChatInterface from '@/components/chat-interface';
import type { ChatMessage, ExtractedMemory } from '@/types';
import * as api from '@/lib/api';

export default function ChatPage() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [isLoading, user, router]);

  const handleSend = async (
    message: string,
    history: ChatMessage[],
    agentRole: string
  ) => {
    if (!token) throw new Error('未登录');
    return api.chat(token, message, history, agentRole);
  };

  const handleSaveExtracted = async (items: ExtractedMemory[]) => {
    if (!token) return;
    try {
      await api.saveExtracted(
        token,
        items.map((m) => ({
          category: m.category,
          key: m.key,
          content: m.content,
          source: 'ai_extracted',
          confidence: m.confidence,
        }))
      );
      alert('记忆已保存！');
    } catch (err) {
      alert(err instanceof Error ? err.message : '保存失败');
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
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100">AI 对话</h1>
        <p className="text-sm text-slate-400">
          切换不同 Agent 角色，验证同一份记忆在不同应用间的效果
        </p>
      </div>
      <div className="h-[calc(100vh-200px)]">
        <ChatInterface onSend={handleSend} onSaveExtracted={handleSaveExtracted} />
      </div>
    </div>
  );
}

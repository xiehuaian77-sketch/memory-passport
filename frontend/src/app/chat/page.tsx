'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import ChatInterface from '@/components/chat-interface';
import type { ChatMessage, Conversation } from '@/types';
import * as api from '@/lib/api';
import { Sparkles, ArrowRight } from 'lucide-react';
import Link from 'next/link';

export default function ChatPage() {
  const { user, token, isLoading } = useAuth();
  const router = useRouter();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractedNotice, setExtractedNotice] = useState<number | null>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [isLoading, user, router]);

  // Load conversations
  const loadConversations = useCallback(async () => {
    if (!token) return;
    try {
      const list = await api.listConversations(token, 20);
      setConversations(list);
      if (list.length > 0 && !activeConversationId) {
        setActiveConversationId(list[0].id);
      }
    } catch {
      // ignore
    }
  }, [token, activeConversationId]);

  useEffect(() => {
    if (token) loadConversations();
  }, [token, loadConversations]);

  // Load messages when activeConversationId changes
  useEffect(() => {
    if (!token || !activeConversationId) return;
    let isMounted = true;
    async function loadMsgs() {
      try {
        const msgs = await api.getConversationMessages(token!, activeConversationId!, 50);
        if (isMounted) {
          setMessages(
            msgs.map((m) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
            }))
          );
        }
      } catch {
        // ignore
      }
    }
    loadMsgs();
    return () => {
      isMounted = false;
    };
  }, [token, activeConversationId]);

  // Create new conversation
  const handleCreateConversation = async () => {
    if (!token) return;
    try {
      const conv = await api.createConversation(token);
      setConversations((prev) => [conv, ...prev]);
      setActiveConversationId(conv.id);
      setMessages([]);
    } catch (err) {
      alert(err instanceof Error ? err.message : '创建会话失败');
    }
  };

  // Delete conversation
  const handleDeleteConversation = async (convId: string) => {
    if (!token) return;
    try {
      await api.deleteConversation(token, convId);
      const remaining = conversations.filter((c) => c.id !== convId);
      setConversations(remaining);
      if (activeConversationId === convId) {
        setActiveConversationId(remaining.length > 0 ? remaining[0].id : null);
        setMessages([]);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除会话失败');
    }
  };

  // Send message
  const handleSend = async (messageText: string, agentRole: string) => {
    if (!token) return;
    setIsSending(true);
    const optimisticMessages: ChatMessage[] = [
      ...messages,
      { role: 'user', content: messageText },
    ];
    setMessages(optimisticMessages);

    try {
      const res = await api.chat(
        token,
        messageText,
        activeConversationId,
        messages,
        agentRole
      );

      const convId = res.conversation_id || activeConversationId;
      if (convId && convId !== activeConversationId) {
        setActiveConversationId(convId);
        loadConversations();
      }

      setMessages([
        ...optimisticMessages,
        { role: 'assistant', content: res.reply || res.response || '' },
      ]);
    } catch (err) {
      setMessages([
        ...optimisticMessages,
        {
          role: 'assistant',
          content: `❌ 请求失败: ${err instanceof Error ? err.message : '网络或服务异常'}`,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  // Extract memory from current conversation
  const handleExtractMemories = async () => {
    if (!token || !activeConversationId) return;
    setIsExtracting(true);
    setExtractedNotice(null);
    try {
      const res = await api.extractMemoryFromConversation(token, activeConversationId);
      if (res.candidates && res.candidates.length > 0) {
        // Tag candidates with source conversation ID
        const candidatesWithConv = res.candidates.map((c) => ({
          ...c,
          source_conversation_id: activeConversationId,
        }));

        // Read existing candidates in localStorage and merge
        let existing = [];
        try {
          const stored = localStorage.getItem('mp_pending_candidates');
          if (stored) existing = JSON.parse(stored);
        } catch {
          existing = [];
        }

        const merged = [...existing, ...candidatesWithConv];
        // Deduplicate by id
        const unique = Array.from(new Map(merged.map((c) => [c.id, c])).values());
        localStorage.setItem('mp_pending_candidates', JSON.stringify(unique));

        setExtractedNotice(res.candidates.length);
      } else {
        alert('当前对话未发现新的明显个人事实或偏好');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '提炼记忆失败');
    } finally {
      setIsExtracting(false);
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
    <div className="mx-auto max-w-7xl px-4 py-6">
      {/* Extracted notice alert banner */}
      {extractedNotice !== null && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-cyan-500/40 bg-cyan-950/40 px-4 py-3 text-sm text-cyan-200 animate-fade-in shadow-lg">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            <span>AI 从当前对话中提炼出 {extractedNotice} 条新记忆候选！</span>
          </div>
          <Link
            href="/dashboard?tab=inbox"
            className="flex items-center gap-1 rounded-lg bg-cyan-600 px-3 py-1 text-xs font-semibold text-white hover:bg-cyan-500 transition-colors"
          >
            前往收件箱授权入库 <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
      )}

      <div className="h-[calc(100vh-170px)]">
        <ChatInterface
          conversations={conversations}
          activeConversationId={activeConversationId}
          messages={messages}
          isLoading={isSending}
          isExtracting={isExtracting}
          onSelectConversation={(id) => setActiveConversationId(id)}
          onCreateConversation={handleCreateConversation}
          onDeleteConversation={handleDeleteConversation}
          onSend={handleSend}
          onExtractMemories={handleExtractMemories}
        />
      </div>
    </div>
  );
}

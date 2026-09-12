'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Send,
  Bot,
  User,
  Loader2,
  Sparkles,
  Plus,
  Trash2,
  MessageSquare,
  Lightbulb,
} from 'lucide-react';
import type { ChatMessage, Conversation } from '@/types';
import { cn, formatDate } from '@/lib/utils';

interface ChatInterfaceProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: ChatMessage[];
  isLoading: boolean;
  isExtracting: boolean;
  onSelectConversation: (id: string) => void;
  onCreateConversation: () => void;
  onDeleteConversation: (id: string) => void;
  onSend: (message: string, agentRole: string) => Promise<void>;
  onExtractMemories: () => Promise<void>;
}

const AGENTS = [
  { id: 'general', label: '通用助手', emoji: '🤖' },
  { id: 'code_assistant', label: '编程助手', emoji: '💻' },
  { id: 'writing_coach', label: '写作教练', emoji: '✍️' },
  { id: 'research_helper', label: '学术助手', emoji: '📚' },
];

export default function ChatInterface({
  conversations,
  activeConversationId,
  messages,
  isLoading,
  isExtracting,
  onSelectConversation,
  onCreateConversation,
  onDeleteConversation,
  onSend,
  onExtractMemories,
}: ChatInterfaceProps) {
  const [input, setInput] = useState('');
  const [agentRole, setAgentRole] = useState('general');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const msg = input.trim();
    setInput('');
    await onSend(msg, agentRole);
  };

  const userMessagesCount = messages.filter((m) => m.role === 'user').length;

  return (
    <div className="flex h-full gap-4">
      {/* Sidebar: Conversation List */}
      <div className="hidden w-64 flex-col rounded-2xl border border-slate-800 bg-slate-900/60 p-3 md:flex">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            历史对话
          </span>
          <button
            onClick={onCreateConversation}
            className="flex items-center gap-1 rounded-lg bg-blue-600/20 border border-blue-500/30 px-2 py-1 text-xs font-medium text-blue-400 hover:bg-blue-600/30 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" /> 新建
          </button>
        </div>

        <div className="flex-1 space-y-1 overflow-y-auto pr-1">
          {conversations.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-600">
              暂无历史会话
            </p>
          ) : (
            conversations.map((c) => {
              const isActive = c.id === activeConversationId;
              return (
                <div
                  key={c.id}
                  onClick={() => onSelectConversation(c.id)}
                  className={cn(
                    'group flex items-center justify-between rounded-xl px-3 py-2 text-xs transition-all cursor-pointer',
                    isActive
                      ? 'bg-blue-600/20 text-blue-300 border border-blue-500/30 font-medium'
                      : 'text-slate-400 hover:bg-slate-800/80 hover:text-slate-200'
                  )}
                >
                  <div className="flex items-center gap-2 truncate">
                    <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">
                      {c.messages && c.messages[0]
                        ? c.messages[0].content
                        : `会话 ${formatDate(c.created_at)}`}
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('确定删除该会话？')) {
                        onDeleteConversation(c.id);
                      }
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-red-400 transition-opacity"
                    title="删除会话"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col rounded-2xl border border-slate-800 bg-slate-900/40 backdrop-blur-xl shadow-xl overflow-hidden">
        {/* Top bar: Agent Switcher + Extract Memory Button */}
        <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 bg-slate-900/60 p-3 gap-2">
          {/* Agent role pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto">
            <span className="text-xs text-slate-500 mr-1 hidden sm:inline">助手角色:</span>
            {AGENTS.map((a) => (
              <button
                key={a.id}
                onClick={() => setAgentRole(a.id)}
                className={cn(
                  'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors',
                  agentRole === a.id
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
                )}
              >
                {a.emoji} {a.label}
              </button>
            ))}
          </div>

          {/* Extract memory trigger */}
          <button
            onClick={onExtractMemories}
            disabled={isExtracting || userMessagesCount === 0 || !activeConversationId}
            className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 px-3 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-600/30 disabled:opacity-40 transition-all"
            title="让 AI 从当前对话中挖掘值得永久记忆的偏好与事实，存入收件箱供你核准"
          >
            {isExtracting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                正在提炼记忆...
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                发现对话记忆
              </>
            )}
          </button>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 py-12 text-center">
              <Bot className="h-12 w-12 mb-3 text-slate-700" />
              <p className="text-base font-semibold text-slate-300">与个性化 AI 对话</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                AI 会自动在你的长期记忆库中检索相关偏好与上下文。你可以随时点击右上角「发现对话记忆」授权沉淀新记忆。
              </p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div
              key={i}
              className={cn(
                'flex gap-3 animate-fade-in',
                msg.role === 'user' ? 'justify-end' : 'justify-start'
              )}
            >
              {msg.role === 'assistant' && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400">
                  <Bot className="h-4 w-4" />
                </div>
              )}

              <div
                className={cn(
                  'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-sm'
                    : 'bg-slate-800/90 text-slate-200 border border-slate-700/60 rounded-bl-sm'
                )}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>

                {/* Assistant memory reference badge (truthful indicator) */}
                {msg.role === 'assistant' && msg.loaded_memories && msg.loaded_memories.length > 0 && (
                  <div className="mt-2 flex items-center gap-1 text-[11px] text-cyan-400/80 border-t border-slate-700/50 pt-1.5">
                    <Lightbulb className="h-3 w-3" />
                    <span>已结合长期记忆 ({msg.loaded_memories.length} 条参考)</span>
                  </div>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-purple-600/20 border border-purple-500/30 text-purple-400">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-3 animate-fade-in">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
              <div className="rounded-2xl rounded-bl-sm bg-slate-800/80 px-4 py-2.5 text-sm text-slate-400 border border-slate-700/60">
                正在结合记忆检索并思考...
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="border-t border-slate-800/80 bg-slate-900/60 p-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder="输入消息，AI 将自动检索记忆回答..."
              className="flex-1 rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none transition-colors"
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2.5 text-white transition-colors hover:bg-blue-500 disabled:opacity-40"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

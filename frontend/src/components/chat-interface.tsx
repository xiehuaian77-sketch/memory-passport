'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import type { ChatMessage, ExtractedMemory, Memory } from '@/types';
import { cn } from '@/lib/utils';

interface ChatInterfaceProps {
  onSend: (
    message: string,
    history: ChatMessage[],
    agentRole: string
  ) => Promise<{
    reply: string;
    extracted_memories: ExtractedMemory[];
    loaded_memories: Memory[];
  }>;
  onSaveExtracted?: (items: ExtractedMemory[]) => void;
}

const AGENTS = [
  { id: 'general', label: '通用助手', emoji: '🤖' },
  { id: 'code_assistant', label: '编程助手', emoji: '💻' },
  { id: 'writing_coach', label: '写作教练', emoji: '✍️' },
  { id: 'research_helper', label: '学术助手', emoji: '📚' },
];

export default function ChatInterface({ onSend, onSaveExtracted }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [agentRole, setAgentRole] = useState('general');
  const [extractedMemories, setExtractedMemories] = useState<ExtractedMemory[]>([]);
  const [loadedMemories, setLoadedMemories] = useState<Memory[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const userMsg = input.trim();
    setInput('');

    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: userMsg }];
    setMessages(newMessages);
    setIsLoading(true);

    try {
      const result = await onSend(userMsg, messages, agentRole);
      setMessages([...newMessages, { role: 'assistant', content: result.reply }]);
      setExtractedMemories(result.extracted_memories);
      setLoadedMemories(result.loaded_memories);
    } catch (err) {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: `❌ 错误: ${err instanceof Error ? err.message : '未知错误'}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full gap-4">
      {/* Chat area */}
      <div className="flex flex-1 flex-col rounded-xl border border-slate-700 bg-slate-800/50">
        {/* Agent selector */}
        <div className="flex items-center gap-2 border-b border-slate-700 p-3">
          <span className="text-xs text-slate-500">切换 Agent:</span>
          {AGENTS.map((a) => (
            <button
              key={a.id}
              onClick={() => setAgentRole(a.id)}
              className={cn(
                'rounded-lg px-2.5 py-1 text-xs font-medium transition-colors',
                agentRole === a.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              )}
            >
              {a.emoji} {a.label}
            </button>
          ))}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <Bot className="h-12 w-12 mb-3 text-slate-600" />
              <p className="text-sm">选择一个 Agent 角色，开始对话</p>
              <p className="text-xs mt-1">AI 将自动加载你的记忆偏好</p>
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
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600/20">
                  <Bot className="h-4 w-4 text-blue-400" />
                </div>
              )}
              <div
                className={cn(
                  'max-w-[75%] rounded-2xl px-4 py-2.5 text-sm',
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-200'
                )}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
              {msg.role === 'user' && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-600/20">
                  <User className="h-4 w-4 text-purple-400" />
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="flex gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600/20">
                <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
              </div>
              <div className="rounded-2xl bg-slate-700 px-4 py-2.5 text-sm text-slate-400">
                思考中...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-700 p-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder="输入消息..."
              className="flex-1 rounded-xl border border-slate-600 bg-slate-700 px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="rounded-xl bg-blue-600 px-4 py-2.5 text-white transition-colors hover:bg-blue-500 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Side panel: loaded + extracted memories */}
      <div className="hidden w-72 flex-col gap-4 lg:flex">
        {/* Loaded memories */}
        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-3">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
            已加载记忆 ({loadedMemories.length})
          </h4>
          <div className="max-h-48 space-y-1.5 overflow-y-auto">
            {loadedMemories.length === 0 && (
              <p className="text-xs text-slate-600">发送消息后显示</p>
            )}
            {loadedMemories.slice(0, 10).map((m) => (
              <div key={m.id} className="rounded-lg bg-slate-700/50 p-2 text-xs">
                <span className="font-medium text-blue-300">{m.key}:</span>{' '}
                <span className="text-slate-400">{m.content}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Extracted memories */}
        {extractedMemories.length > 0 && (
          <div className="rounded-xl border border-green-500/20 bg-green-900/10 p-3">
            <h4 className="mb-2 text-xs font-semibold uppercase text-green-400">
              AI 提取的新记忆
            </h4>
            <div className="space-y-1.5">
              {extractedMemories.map((m, i) => (
                <div key={i} className="rounded-lg bg-slate-700/50 p-2 text-xs">
                  <span className="font-medium text-green-300">{m.key}:</span>{' '}
                  <span className="text-slate-400">{m.content}</span>
                  <span className="ml-1 text-slate-600">
                    ({(m.confidence * 100).toFixed(0)}%)
                  </span>
                </div>
              ))}
            </div>
            {onSaveExtracted && (
              <button
                onClick={() => onSaveExtracted(extractedMemories)}
                className="mt-2 w-full rounded-lg bg-green-600/20 py-1.5 text-xs font-medium text-green-300 hover:bg-green-600/30"
              >
                保存这些记忆
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

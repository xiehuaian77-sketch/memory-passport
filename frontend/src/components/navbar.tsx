'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Brain, LayoutDashboard, MessageSquare, User, LogOut, Settings, BarChart3 } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { href: '/chat', label: 'AI 对话', icon: MessageSquare },
  { href: '/dashboard', label: '记忆中心', icon: LayoutDashboard },
  { href: '/dashboard/evaluation', label: '评测中心', icon: BarChart3 },
  { href: '/settings', label: '策略设置', icon: Settings },
  { href: '/identity', label: '身份管理', icon: User },
];

export default function Navbar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <Brain className="h-7 w-7 text-blue-400" />
          <span className="text-lg font-bold gradient-text">Memory Passport</span>
        </Link>

        {/* Nav Links */}
        <div className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-blue-500/20 text-blue-300'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
        </div>

        {/* User */}
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <span className="text-sm text-slate-400">{user.display_name}</span>
              <button
                onClick={logout}
                className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800 hover:text-red-400"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
            >
              登录
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}

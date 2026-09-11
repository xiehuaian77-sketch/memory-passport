import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import Navbar from '@/components/navbar';

export const metadata: Metadata = {
  title: 'Memory Passport — 可迁移的 AI 记忆身份层',
  description: '让 AI 真正记住你。可迁移、可控制、可追溯的 AI 记忆管理协议。',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="min-h-screen bg-slate-950">
        <AuthProvider>
          <Navbar />
          <main className="pt-16">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}

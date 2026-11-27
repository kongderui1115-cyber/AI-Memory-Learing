import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import { AuthProvider } from '@/components/AuthProvider';
import { AppShell } from '@/components/AppShell';

export const metadata: Metadata = {
  title: '学习记忆 OS · AI 学习复习系统',
  description: '把学习笔记结构化成知识点，用艾宾浩斯与 FSRS 调度安排每日复习。',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#0f766e',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}

'use client';

/**
 * 中文 UI 基础布局（FE-02）：移动端优先。
 * 手机端为顶部紧凑标题栏 + 底部标签栏；桌面端为顶部横向导航。
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useAuth } from './AuthProvider';
import { LoginPanel } from './LoginPanel';
import { Loading } from './States';

const reviewIcon = (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="3" width="16" height="18" rx="2" />
    <path d="M8 8h8M8 12h8M8 16h4" />
    <path d="m15 16 1.5 1.5 3-3" />
  </svg>
);

const knowledgeIcon = (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5z" />
    <path d="M4 17.5h16M9 7h7" />
  </svg>
);

interface NavItem {
  href: string;
  label: string;
  icon: ReactNode;
}

const NAV: NavItem[] = [
  { href: '/dashboard', label: '学习总览', icon: reviewIcon },
  { href: '/statistics', label: '学习统计', icon: knowledgeIcon },
  { href: '/settings', label: '设置', icon: knowledgeIcon },
  { href: '/review', label: '今日复习', icon: reviewIcon },
  { href: '/knowledge', label: '知识管理', icon: knowledgeIcon },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { ready, authenticated, email, signOut } = useAuth();
  const pathname = usePathname() ?? '';

  // Keep preview and framework error pages outside the legacy business layout.
  const usesBusinessLayout = NAV.some((item) => pathname === item.href) || pathname.startsWith('/knowledge/');
  if (!usesBusinessLayout) return <>{children}</>;

  if (!ready) {
    return (
      <div className="boot">
        <Loading text="正在初始化…" />
      </div>
    );
  }

  if (!authenticated) return <LoginPanel />;

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__inner">
          <Link href="/review" className="brand">
            <span className="brand__mark" aria-hidden="true">记</span>
            <span className="brand__text">
              <strong>学习记忆 OS</strong>
              <small>AI 学习 · 记忆 · 复习</small>
            </span>
          </Link>

          <nav className="desktop-nav" aria-label="主导航">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-link ${isActive(item.href) ? 'nav-link--active' : ''}`}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            ))}
          </nav>

          <div className="header-user">
            <span className="header-user__email" title={email ?? ''}>{email ?? '已登录'}</span>
            <button type="button" className="btn btn--ghost btn--sm" onClick={signOut}>
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">{children}</main>

      <footer className="app-footer">
        <span>数据来自真实后端 API（/api/v1）；未配置、请求失败或无数据时会如实提示，不使用模拟数据。</span>
      </footer>

      <nav className="mobile-tabbar" aria-label="底部导航">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`tab ${isActive(item.href) ? 'tab--active' : ''}`}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </div>
  );
}

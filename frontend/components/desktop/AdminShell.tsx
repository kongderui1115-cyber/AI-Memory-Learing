"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Bell,
  BrainCircuit,
  Database,
  Gauge,
  History,
  Layers3,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { adminHref, adminNavigation } from "./admin-console-data";
import { AdminDemoProvider } from "./AdminDemoProvider";

const icons = [Gauge, Sparkles, Database, Bell, Layers3, Users, History];
export default function AdminShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const current = adminNavigation.find((item) => adminHref(item.id) === path);
  return (
    <div className="desktop-os ac-shell">
      <AdminDemoProvider>
        <aside className="ds-sidebar">
          <Link className="ds-brand" href="/preview/admin">
            <span className="ds-brand-mark">
              <BrainCircuit size={30} />
            </span>
            <span>
              <strong>AI 学习记忆系统</strong>
              <small>ADMIN WORKSPACE</small>
            </span>
          </Link>
          <span className="ac-sidebar-caption">系统管理</span>
          <nav
            className="ds-navigation ds-admin-console-nav"
            aria-label="管理员导航"
          >
            {adminNavigation.map((item, index) => {
              const Icon = icons[index];
              return (
                <Link
                  key={item.id}
                  href={adminHref(item.id)}
                  className={path === adminHref(item.id) ? "active" : ""}
                >
                  <Icon size={19} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
          <div className="ac-sidebar-note">
            <ShieldCheck size={19} />
            <strong>管理员工作空间</strong>
            <p>管理配置、学习进度与系统活动。</p>
          </div>
          <div className="ds-sidebar-bottom">
            <Link href="/preview">
              <ArrowLeft size={18} />
              返回用户端
            </Link>
            <div className="ac-admin-profile">
              <span className="ds-mini-avatar">Z</span>
              <span>
                <strong>zi rui</strong>
                <small>管理员 · 界面演示</small>
              </span>
              <Settings2 size={16} />
            </div>
          </div>
        </aside>
        <div className="ds-workspace">
          <header className="ds-header">
            <div>
              <h1>{current?.label ?? "管理员后台"}</h1>
              <p>管理员工作空间 / {current?.label ?? "系统管理"}</p>
            </div>
            <div className="ac-top-actions">
              <span>
                <i />
                前端演示环境
              </span>
              <Link href="/preview/push">
                查看推送阅读页 <ArrowUpRight size={14} />
              </Link>
            </div>
          </header>
          <div className="ds-preview-bar">
            <span>
              <span className="ds-preview-dot" />
              独立管理员后台 · 示例数据
            </span>
            <span>所有服务状态、在线情况与操作结果均为前端演示</span>
          </div>
          <main className="ds-main ac-main">{children}</main>
          <footer className="ds-footer">
            <BrainCircuit size={14} />
            <span>AI Learning Memory OS</span>
            <span>管理后台界面预览</span>
          </footer>
        </div>
      </AdminDemoProvider>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDownRight, ChevronRight, FlaskConical, LogOut, Menu, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createAdminClient, type AdminMode } from "@/lib/client";
import { navigation, sectionPath, type Section } from "@/lib/routes";
import Dashboard from "./dashboard/Dashboard";
import Management from "./management/Management";
import { Brand } from "./brand";

const groups = ["总览", "配置", "运维"] as const;

export function AdminShell({ section, mode }: { section: Section; mode: AdminMode }) {
  const router = useRouter();
  const demo = mode === "demo";
  const client = useMemo(() => createAdminClient(mode), [mode]);
  const [principal, setPrincipal] = useState<Awaited<ReturnType<typeof client.session>> | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [menu, setMenu] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [reload, setReload] = useState(0);
  const active = navigation.find((item) => item.id === section);

  useEffect(() => {
    if (demo) return;
    let current = true;
    client.session().then((user) => {
      if (current) setPrincipal(user);
    }).catch((error: unknown) => {
      if (!current) return;
      const status = typeof error === "object" && error !== null && "status" in error ? error.status : undefined;
      if (status === 401 || status === 403) router.replace("/login");
      else setSessionError("无法验证管理员会话。请检查统一 API 后重试。");
    });
    return () => { current = false; };
  }, [client, demo, reload, router]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setMenu(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function logout() {
    setLeaving(true);
    try {
      await client.logout();
      router.replace("/login");
    } catch {
      setSessionError("退出失败，请重试。");
    } finally {
      setLeaving(false);
    }
  }

  if (!demo && !principal) {
    return <main className="admin-gate"><Brand /><section className="admin-gate-card">
      <ShieldCheck size={24} aria-hidden="true" />
      <h1>{sessionError ? "会话验证失败" : "正在验证管理员身份"}</h1>
      <p role="status">{sessionError || "正在连接统一 API。"}</p>
      {sessionError && <div className="admin-gate-actions">
        <button className="admin-primary" onClick={() => { setSessionError(""); setReload(reload + 1); }}>重试</button>
        <Link href="/login">返回登录</Link>
      </div>}
    </section></main>;
  }

  const name = demo ? "演示管理员" : principal?.display_name || principal?.email || "管理员";
  return (
    <div className="admin-frame">
      <a href="#console-content" className="admin-skip">跳至内容</a>
      {menu && <button className="admin-scrim" aria-label="关闭导航" onClick={() => setMenu(false)} />}
      <aside className={`admin-sidebar${menu ? " admin-sidebar-open" : ""}`}>
        <Link href={sectionPath("dashboard", demo)} className="admin-logo-link" onClick={() => setMenu(false)}><Brand /></Link>
        <nav aria-label="管理导航">
          {groups.map((group) => <div className="admin-nav-group" key={group}>
            <small>{group}</small>
            {navigation.filter((item) => item.group === group).map(({ id, label, icon: Icon }) => (
              <Link href={sectionPath(id, demo)} key={id} aria-current={section === id ? "page" : undefined} onClick={() => setMenu(false)}>
                <Icon size={17} strokeWidth={1.75} aria-hidden="true" /><span>{label}</span>
                {section === id && <ChevronRight size={14} aria-hidden="true" />}
              </Link>
            ))}
          </div>)}
        </nav>
        <div className="admin-sidebar-foot">
          <span className="admin-avatar" aria-hidden="true">{demo ? "演" : name.slice(0, 1).toUpperCase()}</span>
          <span><strong>{name}</strong><small>{demo ? "独立演示会话" : "管理员"}</small></span>
          {demo ? <Link href="/login" title="管理员登录" aria-label="管理员登录"><ArrowDownRight size={16} /></Link> :
            <button type="button" title="退出登录" aria-label="退出登录" disabled={leaving} onClick={logout}><LogOut size={16} /></button>}
        </div>
      </aside>
      <section className="admin-workspace">
        <header className="admin-topbar">
          <button type="button" className="admin-menu" aria-expanded={menu} aria-label={menu ? "关闭导航" : "打开导航"} onClick={() => setMenu(!menu)}>
            {menu ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div className="admin-crumb"><span>控制台</span><ChevronRight size={13} aria-hidden="true" /><strong>{active?.label}</strong></div>
          {demo ? <Link href="/login" className="admin-mode admin-mode-demo"><FlaskConical size={14} aria-hidden="true" /> 演示数据</Link>
            : <span className="admin-mode"><ShieldCheck size={14} aria-hidden="true" /> 已验证管理员</span>}
        </header>
        <main id="console-content" className="admin-content">
          {demo && <aside className="admin-demo-notice"><FlaskConical size={16} aria-hidden="true" /><span>演示模式 · 图表和操作使用示例数据，刷新页面后重置。</span></aside>}
          {sessionError && <p role="alert" className="admin-error">{sessionError}</p>}
          {section === "dashboard" ? <Dashboard mode={mode} client={client} accountTimezone={principal?.timezone} /> : <Management section={section} mode={mode} client={client} />}
        </main>
      </section>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, FlaskConical, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { createAdminClient } from "@/lib/client";
import { Brand } from "./brand";

export function LoginForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await createAdminClient("live").login(String(values.get("email")).trim(), String(values.get("password")));
      router.replace("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "登录失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="admin-login">
      <div className="admin-login-visual">
        <Brand />
        <div className="admin-orbit" aria-hidden="true"><i /><i /><i /><i /><b /></div>
        <div className="admin-login-pitch">
          <h1>学习记忆系统<br />管理控制台</h1>
          <p>集中查看学习数据、记忆表现与后台服务。</p>
        </div>
      </div>
      <section className="admin-login-form">
        <div className="admin-login-inner">
          <span className="admin-login-icon"><ShieldCheck size={24} aria-hidden="true" /></span>
          <h2>管理员登录</h2>
          <p>使用项目中已有的管理员账号。</p>
          <form onSubmit={submit}>
            <label htmlFor="admin-email">管理员邮箱</label>
            <input id="admin-email" name="email" type="email" maxLength={254} autoComplete="username" required />
            <label htmlFor="admin-password">密码</label>
            <div className="admin-password">
              <input id="admin-password" name="password" type={visible ? "text" : "password"} maxLength={256} autoComplete="current-password" required />
              <button type="button" aria-label={visible ? "隐藏密码" : "显示密码"} onClick={() => setVisible(!visible)}>
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {error && <p className="admin-error" role="alert">{error}</p>}
            <button type="submit" className="admin-primary" disabled={busy}>{busy ? "正在验证…" : "进入管理控制台"}<ArrowRight size={17} aria-hidden="true" /></button>
          </form>
          <Link className="admin-demo-link" href="/demo"><FlaskConical size={16} aria-hidden="true" /> 体验演示控制台 <ArrowRight size={15} aria-hidden="true" /></Link>
        </div>
      </section>
    </main>
  );
}

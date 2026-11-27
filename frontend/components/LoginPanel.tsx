"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { useAuth } from "./AuthProvider";
import { ErrorView } from "./States";
import "../app/preview/desktop.css";

/** Styled login retains the existing real API authentication entry point. */
export function LoginPanel() {
  const { signIn, pending, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await signIn(email.trim(), password);
  }

  return (
    <div className="desktop-os ds-auth-screen">
      <section className="ds-auth-story">
        <div className="ds-auth-brand">
          <span className="ds-brand-mark">
            <BrainCircuit size={30} />
          </span>
          <span>
            <strong>AI 学习记忆系统</strong>
            <small>AI Learning Memory OS</small>
          </span>
        </div>
        <div className="ds-auth-message">
          <span>让知识成为你的一部分</span>
          <h1>
            每一次学习，
            <br />
            都值得长久记住。
          </h1>
          <p>
            连接你的笔记，理解知识的脉络，
            <br />
            让恰好的复习陪你走得更远。
          </p>
          <div>
            <i />
            <i />
            <i />
          </div>
        </div>
        <small className="ds-auth-copyright">学习 · 理解 · 记忆 · 成长</small>
      </section>
      <section className="ds-auth-form-area">
        <Link href="/preview" className="ds-auth-back">
          <ArrowLeft size={15} />
          返回界面预览
        </Link>
        <div className="ds-auth-form-card">
          <span className="ds-auth-symbol">
            <BrainCircuit size={29} />
          </span>
          <h2>欢迎回到学习空间</h2>
          <p>登录你的账号，继续今天的学习。</p>
          <form onSubmit={handleSubmit}>
            <label htmlFor="login-email">邮箱地址</label>
            <div className="ds-auth-input">
              <Mail size={17} />
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="输入你的邮箱"
                required
              />
            </div>
            <label htmlFor="login-password">密码</label>
            <div className="ds-auth-input">
              <LockKeyhole size={17} />
              <input
                id="login-password"
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="输入你的密码"
                required
                minLength={8}
              />
              <button
                type="button"
                aria-label={visible ? "隐藏密码" : "显示密码"}
                onClick={() => setVisible((previous) => !previous)}
              >
                {visible ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>
            <button
              className="ds-button primary ds-auth-submit"
              type="submit"
              disabled={pending}
            >
              {pending ? (
                <>
                  <LoaderCircle size={17} className="ds-spin" />
                  正在登录…
                </>
              ) : (
                <>
                  进入学习空间
                  <ArrowRight size={17} />
                </>
              )}
            </button>
          </form>
          {error && (
            <div className="ds-auth-error">
              <ErrorView error={error} showRelogin={false} />
            </div>
          )}
          <div className="ds-auth-footnote">
            <ShieldCheck size={14} />
            登录表单连接已配置的后端账号接口
          </div>
        </div>
        <span className="ds-auth-form-footer">AI Learning Memory OS</span>
      </section>
    </div>
  );
}

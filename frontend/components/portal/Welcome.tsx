"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  BrainCircuit,
  CalendarDays,
  Eye,
  EyeOff,
  LoaderCircle,
  Mail,
} from "lucide-react";
import { useAuth } from "@/components/AuthProvider";
import { learningDestination, webApi } from "@/lib/workspace";
import type { WorkspaceData } from "@/lib/workspace";
import "./portal.css";

export default function Welcome() {
  const router = useRouter();
  const params = useSearchParams();
  const destination = learningDestination(params.get("next"));
  const auth = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (auth.ready && auth.authenticated) {
      webApi<WorkspaceData>("/workspace/settings")
        .then((data) =>
          router.replace(
            data.profile.onboarding_completed_at
              ? destination
              : "/onboarding" +
                  (destination === "/app"
                    ? ""
                    : "?next=" + encodeURIComponent(destination)),
          ),
        )
        .catch((e) => setError(e.message));
    }
  }, [auth.ready, auth.authenticated, router, destination]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode === "register" && password !== confirm) {
      setError("两次密码输入不一致");
      return;
    }
    setPending(true);
    try {
      if (mode === "register") {
        await webApi("/auth/register", {
          method: "POST",
          body: { display_name: name.trim(), email, password },
        });
        await auth.refresh();
      } else {
        const ok = await auth.signIn(email, password);
        if (!ok) return;
      }
      setPassword("");
      setConfirm("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="portal portal-welcome">
      <section className="portal-story">
        <a className="portal-brand" href="/">
          <BrainCircuit size={35} />
          <span>
            <strong>AI 学习记忆系统</strong>
            <small>AI Learning Memory OS</small>
          </span>
        </a>
        <div className="portal-story-copy">
          <h1>
            每一次学习，
            <br />
            都值得长久记住。
          </h1>
          <p>
            连接你的笔记，理解知识的脉络。
            <br />
            让恰好的复习，陪你走得更远。
          </p>
          <div className="portal-story-features">
            <span>
              <BookOpen size={19} />
              连接 Notion 笔记
            </span>
            <span>
              <CalendarDays size={19} />
              个性化间隔复习
            </span>
            <span>
              <Mail size={19} />
              邮件复习陪伴
            </span>
          </div>
        </div>
        <footer>学习 · 理解 · 记忆 · 成长</footer>
      </section>
      <main className="portal-entry">
        <div className="portal-auth-card">
          <div className="portal-tabs" role="tablist" aria-label="账户操作">
            <button
              role="tab"
              aria-selected={mode === "login"}
              onClick={() => {
                setMode("login");
                setError("");
              }}
            >
              登录
            </button>
            <button
              role="tab"
              aria-selected={mode === "register"}
              onClick={() => {
                setMode("register");
                setError("");
              }}
            >
              注册
            </button>
          </div>
          <h2>{mode === "login" ? "欢迎回来" : "开启你的学习旅程"}</h2>
          <p className="portal-muted">
            {mode === "login"
              ? "登录你的专属知识与记忆空间。"
              : "创建账户后，我们会陪你一步步完成设置。"}
          </p>
          <form onSubmit={submit}>
            {mode === "register" && (
              <label>
                称呼
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={120}
                  autoComplete="nickname"
                  placeholder="希望我们如何称呼你"
                />
              </label>
            )}
            <label>
              账号邮箱
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
                placeholder="you@example.com"
              />
            </label>
            <label>
              登录密码
              <div className="portal-password">
                <input
                  type={visible ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={mode === "register" ? 10 : 8}
                  maxLength={256}
                  autoComplete={
                    mode === "register" ? "new-password" : "current-password"
                  }
                  placeholder={
                    mode === "register" ? "至少 10 位字符" : "输入密码"
                  }
                />
                <button
                  type="button"
                  aria-label={visible ? "隐藏密码" : "显示密码"}
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </label>
            {mode === "register" && (
              <>
                <label>
                  确认密码
                  <input
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    required
                    minLength={10}
                    autoComplete="new-password"
                    placeholder="再次输入密码"
                  />
                </label>
                <p className="portal-help">
                  密码至少 10 位。连续登录失败超过 5 次将暂时锁定。
                </p>
              </>
            )}
            {(error || auth.error) && (
              <p className="portal-error" role="alert">
                {error || auth.error?.message}
              </p>
            )}
            <button
              className="portal-primary portal-wide"
              disabled={pending || auth.pending}
            >
              {pending || auth.pending ? (
                <LoaderCircle className="portal-spin" size={18} />
              ) : (
                <>
                  {mode === "login" ? "登录" : "创建账户"}
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
          <p className="portal-auth-note">
            你的笔记、复习进度和个人配置，随账户保存。
          </p>
        </div>
      </main>
    </div>
  );
}

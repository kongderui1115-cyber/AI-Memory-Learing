"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { UserPlus, X } from "lucide-react";
import { webApi } from "@/lib/workspace";
import type { PortalUser } from "@/lib/workspace";

const emptyForm = {
  display_name: "",
  email: "",
  password: "",
  confirmation: "",
  role: "user" as "user" | "admin",
};

export default function AdminUserForm({
  onCreated,
}: {
  onCreated: (user: PortalUser) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<{ payload: string; key: string } | null>(null);
  const inFlight = useRef(false);
  const [form, setForm] = useState(emptyForm);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  function close() {
    if (inFlight.current) return;
    dialog.current?.close();
    setForm(emptyForm);
    setError("");
    request.current = null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    setError("");
    if (!form.display_name.trim()) {
      setError("请填写用户称呼");
      return;
    }
    if (form.password.trim().length < 10) {
      setError("密码至少包含 10 个有效字符");
      return;
    }
    if (form.password !== form.confirmation) {
      setError("两次密码输入不一致");
      return;
    }
    const body = {
      display_name: form.display_name.trim(),
      email: form.email.trim(),
      password: form.password,
      role: form.role,
    };
    const payload = JSON.stringify(body);
    if (request.current?.payload !== payload)
      request.current = { payload, key: crypto.randomUUID() };
    inFlight.current = true;
    setPending(true);
    let created: PortalUser;
    try {
      created = await webApi<PortalUser>("/admin/users", {
        method: "POST",
        body,
        key: request.current.key,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建用户失败，请重试");
      return;
    } finally {
      inFlight.current = false;
      setPending(false);
    }
    close();
    onCreated(created);
  }

  return (
    <>
      <button
        className="portal-primary"
        type="button"
        onClick={() => dialog.current?.showModal()}
      >
        <UserPlus size={17} />
        添加用户
      </button>
      <dialog
        ref={dialog}
        className="portal portal-dialog"
        aria-label="添加用户"
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        <button
          className="portal-dialog-close"
          type="button"
          aria-label="关闭添加用户"
          disabled={pending}
          onClick={close}
        >
          <X size={20} />
        </button>
        <h2>添加用户</h2>
        <form onSubmit={submit}>
          <fieldset className="portal-create-fields" disabled={pending}>
            <label>
              用户称呼
              <input
                required
                maxLength={120}
                autoComplete="off"
                value={form.display_name}
                onChange={(event) =>
                  setForm({ ...form, display_name: event.target.value })
                }
              />
            </label>
            <label>
              用户邮箱
              <input
                required
                type="email"
                maxLength={254}
                autoComplete="off"
                value={form.email}
                onChange={(event) =>
                  setForm({ ...form, email: event.target.value })
                }
              />
            </label>
            <label>
              初始密码
              <input
                required
                type="password"
                minLength={10}
                maxLength={256}
                autoComplete="new-password"
                placeholder="至少 10 个有效字符"
                value={form.password}
                onChange={(event) =>
                  setForm({ ...form, password: event.target.value })
                }
              />
            </label>
            <label>
              确认初始密码
              <input
                required
                type="password"
                minLength={10}
                maxLength={256}
                autoComplete="new-password"
                value={form.confirmation}
                onChange={(event) =>
                  setForm({ ...form, confirmation: event.target.value })
                }
              />
            </label>
            <label>
              用户角色
              <select
                aria-label="用户角色"
                value={form.role}
                onChange={(event) =>
                  setForm({
                    ...form,
                    role: event.target.value as "user" | "admin",
                  })
                }
              >
                <option value="user">普通用户</option>
                <option value="admin">管理员</option>
              </select>
            </label>
          </fieldset>
          {error && (
            <p className="portal-error" role="alert">
              {error}
            </p>
          )}
          <div className="portal-create-actions">
            <button
              className="portal-secondary"
              type="button"
              disabled={pending}
              onClick={close}
            >
              取消
            </button>
            <button className="portal-primary" type="submit" disabled={pending}>
              {pending ? "正在创建…" : "创建用户"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}

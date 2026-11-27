"use client";
import Link from "next/link";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import AdminPreview from "./AdminPreview";
import { adminPreviewUsers } from "./admin-preview-data";
import { sampleSessions } from "./admin-console-data";
import { AdminPanel, AdminStatus } from "./AdminUi";
import { useAdminDemo } from "./AdminDemoProvider";

export default function AdminUsers() {
  const { notify } = useAdminDemo();
  const [user, setUser] = useState("all");
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const invalidRange = Boolean(from && to && from > to);
  const sessions = sampleSessions.filter(
    (session) =>
      !invalidRange &&
      (user === "all" || session.userId === user) &&
      (status === "all" || (status === "online") === session.online) &&
      (!from || session.login >= from) &&
      (!to || session.login <= `${to}:59`),
  );
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>登录活动与学习情况</h2>
          <p>查看谁在什么时间登录、会话何时结束，以及当前示例在线状态。</p>
        </div>
        <button
          className="ds-button"
          onClick={() =>
            notify("在线状态演示已刷新，未查询服务器。快照时间为 11-13 20:00。")
          }
        >
          <RefreshCw size={15} />
          刷新演示状态
        </button>
      </div>
      <div id="sessions">
        <AdminPanel
          title="登录记录与在线状态"
          action={
            <AdminStatus tone="green">2 位用户在线 · 示例快照</AdminStatus>
          }
        >
          <div className="ac-session-filters">
            <label>
              用户
              <select
                aria-label="筛选登录用户"
                value={user}
                onChange={(event) => setUser(event.target.value)}
              >
                <option value="all">全部用户</option>
                {adminPreviewUsers.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              在线状态
              <select
                aria-label="筛选在线状态"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="all">全部状态</option>
                <option value="online">在线</option>
                <option value="offline">离线</option>
              </select>
            </label>
            <label>
              登录起始时间
              <input
                type="datetime-local"
                aria-label="登录起始时间"
                value={from}
                onChange={(event) => setFrom(event.target.value)}
              />
            </label>
            <label>
              登录结束时间
              <input
                type="datetime-local"
                aria-label="登录结束时间"
                value={to}
                onChange={(event) => setTo(event.target.value)}
              />
            </label>
            <button
              className="ac-link-button"
              onClick={() => {
                setFrom("");
                setTo("");
                setUser("all");
                setStatus("all");
              }}
            >
              清空筛选
            </button>
          </div>
          {invalidRange && (
            <p role="alert" className="ac-form-error">
              起始时间应早于结束时间。
            </p>
          )}
          <p className="ac-muted ac-session-note">
            时间均为 Asia/Shanghai。在线状态来自 2026-11-13 20:00 的演示快照。
          </p>
          <div className="ds-table-wrap">
            <table aria-label="用户登录会话">
              <thead>
                <tr>
                  <th>用户</th>
                  <th>状态</th>
                  <th>登录时间</th>
                  <th>退出 / 会话结束</th>
                  <th>最后活跃</th>
                  <th>IP / 设备</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr key={session.id}>
                    <td>{session.name}</td>
                    <td>
                      <span
                        className={`ac-online-state ${session.online ? "online" : ""}`}
                      >
                        <i />
                        {session.online ? "在线" : "离线"}
                      </span>
                    </td>
                    <td>{session.login.replace("T", " ")}</td>
                    <td>
                      {session.logout?.replace("T", " ") ??
                        "会话进行中（示例）"}
                    </td>
                    <td>{session.lastActive.replace("T", " ")}</td>
                    <td>
                      {session.ip}
                      <small className="ds-admin-table-subject">
                        {session.device}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sessions.length === 0 && (
              <div className="ds-empty">当前筛选下没有登录记录</div>
            )}
          </div>
          <div className="ac-session-footer">
            <span>共 {sessions.length} 条示例会话</span>
            <Link className="ds-text-link" href="/preview/admin/security">
              查看相关安全日志
            </Link>
          </div>
        </AdminPanel>
      </div>
      <div className="ds-spaced-panel">
        <AdminPreview users={adminPreviewUsers} />
      </div>
    </>
  );
}

"use client";
import { useState } from "react";
import { Search, ShieldCheck } from "lucide-react";
import { useAdminDemo } from "./AdminDemoProvider";
import { AdminDialog, AdminPanel, AdminStatus } from "./AdminUi";
import type { SecurityEvent } from "./admin-console-data";

export default function AdminSecurity() {
  const { state } = useAdminDemo();
  const [level, setLevel] = useState("all");
  const [action, setAction] = useState("all");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<SecurityEvent | null>(null);
  const events = state.securityEvents.filter(
    (event) =>
      (level === "all" || event.level === level) &&
      (action === "all" || event.action === action) &&
      `${event.actor} ${event.target} ${event.ip}`
        .toLowerCase()
        .includes(query.toLowerCase().trim()),
  );
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>安全事件与管理审计</h2>
          <p>查看登录、访问拦截及管理活动的示例记录。</p>
        </div>
        <AdminStatus>示例日志</AdminStatus>
      </div>
      <div className="ac-security-summary">
        {["信息", "警告", "高风险"].map((label) => (
          <section key={label}>
            <ShieldCheck size={22} />
            <div>
              <small>{label}事件</small>
              <strong>
                {
                  state.securityEvents.filter((event) => event.level === label)
                    .length
                }
              </strong>
            </div>
          </section>
        ))}
      </div>
      <AdminPanel title="安全日志">
        <div className="ac-log-filters">
          <label className="ds-admin-search">
            <Search size={15} />
            <input
              aria-label="搜索安全日志"
              placeholder="搜索用户、目标或 IP"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <select
            aria-label="筛选安全级别"
            value={level}
            onChange={(event) => setLevel(event.target.value)}
          >
            <option value="all">全部级别</option>
            {["信息", "警告", "高风险"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <select
            aria-label="筛选安全事件"
            value={action}
            onChange={(event) => setAction(event.target.value)}
          >
            <option value="all">全部事件</option>
            {Array.from(
              new Set(state.securityEvents.map((event) => event.action)),
            ).map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </div>
        <div className="ds-table-wrap">
          <table aria-label="安全事件日志">
            <thead>
              <tr>
                <th>时间</th>
                <th>用户</th>
                <th>事件</th>
                <th>级别</th>
                <th>结果</th>
                <th>来源 IP</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>{event.time}</td>
                  <td>{event.actor}</td>
                  <td>{event.action}</td>
                  <td>
                    <AdminStatus
                      tone={
                        event.level === "高风险"
                          ? "red"
                          : event.level === "警告"
                            ? "orange"
                            : "neutral"
                      }
                    >
                      {event.level}
                    </AdminStatus>
                  </td>
                  <td>{event.result}</td>
                  <td>{event.ip}</td>
                  <td>
                    <button
                      className="ac-link-button"
                      aria-label={`查看日志 ${event.id}`}
                      onClick={() => setDetail(event)}
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {events.length === 0 && (
            <div className="ds-empty">没有符合条件的安全日志</div>
          )}
        </div>
      </AdminPanel>
      <AdminPanel title="账号安全要求" className="ds-spaced-panel">
        <div className="ac-security-requirements">
          <div>
            <strong>密码规则</strong>
            <p>
              继承用户提出的至少10位要求，具体字符规则与正式校验在后端阶段落实。
            </p>
          </div>
          <div>
            <strong>失败登录限制</strong>
            <p>连续失败超过5次时限时限制，管理员可从安全日志查看相关事件。</p>
          </div>
          <div>
            <strong>访问与审计</strong>
            <p>按角色和目标用户校验访问范围，记录管理访问及配置变更。</p>
          </div>
        </div>
        <p className="ac-inline-demo">
          当前页面仅展示安全要求和示例事件，正式安全控制与在线会话由后端实现并验证。
        </p>
      </AdminPanel>
      {detail && (
        <AdminDialog title="安全事件详情" close={() => setDetail(null)}>
          <dl className="ac-event-detail">
            {[
              { label: "事件编号", value: detail.id },
              { label: "发生时间", value: detail.time },
              { label: "操作用户", value: detail.actor },
              { label: "操作类型", value: detail.action },
              { label: "访问目标", value: detail.target },
              { label: "来源 IP", value: detail.ip },
              { label: "结果", value: detail.result },
            ].map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
          <p className="ac-muted">这是用于管理员界面检查的示例审计记录。</p>
        </AdminDialog>
      )}
    </>
  );
}

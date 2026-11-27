"use client";
import { useState } from "react";
import { createPreviewId } from "./preview-id";
import { Bell, Check, Eye, Send, Settings2 } from "lucide-react";
import { useAdminDemo } from "./AdminDemoProvider";
import { AdminDialog, AdminPanel, AdminStatus, AdminToggle } from "./AdminUi";
import { templateValues } from "./admin-console-data";
import type { ChannelConfig } from "./admin-console-data";

export default function AdminNotifications() {
  const { state, setState, notify } = useAdminDemo();
  const [channel, setChannel] = useState<ChannelConfig | null>(null);
  const [template, setTemplate] = useState(state.template);
  const [error, setError] = useState("");
  const [historyChannel, setHistoryChannel] = useState("all");
  const [history, setHistory] = useState([
    {
      id: "message-1",
      channel: "PushPlus",
      user: "zi rui",
      time: "11-13 19:00",
      status: "示例已发送",
    },
    {
      id: "message-2",
      channel: "钉钉",
      user: "林予",
      time: "11-13 19:00",
      status: "示例待重试",
    },
  ]);
  const unknown = Array.from(template.matchAll(/{{\s*([\w]+)\s*}}/g))
    .map((match) => match[1])
    .filter((key) => !Object.hasOwn(templateValues, key));
  const preview = template.replace(
    /{{\s*([\w]+)\s*}}/g,
    (match, key: string) =>
      Object.hasOwn(templateValues, key) ? templateValues[key] : match,
  );
  function sendDemo(value: ChannelConfig) {
    if (!value.enabled || !value.configured) {
      notify("请先启用并配置该渠道的演示状态。");
      return;
    }
    setHistory((previous) => [
      {
        id: createPreviewId(),
        channel: value.name,
        user: "演示接收用户",
        time: "本次演示",
        status: "前端演示完成 · 未投递",
      },
      ...previous,
    ]);
    notify("测试发送流程已演示，未调用消息接口。");
  }
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>通知渠道与复习内容</h2>
          <p>按用户绑定接收身份，推送知识正文、回忆问题和原始来源。</p>
        </div>
        <AdminStatus>全部为前端演示</AdminStatus>
      </div>
      <div className="ac-channel-grid">
        {state.channels.map((item) => (
          <section className="ds-panel ac-channel-card" key={item.id}>
            <div className="ac-card-top">
              <span className="ac-provider-symbol teal">
                <Bell size={21} />
              </span>
              <div>
                <h2>{item.name}</h2>
                <small>{item.description}</small>
              </div>
              <AdminToggle
                label={`启用 ${item.name}通知`}
                checked={item.enabled}
                onChange={() =>
                  setState((previous) => ({
                    ...previous,
                    channels: previous.channels.map((value) =>
                      value.id === item.id
                        ? { ...value, enabled: !value.enabled }
                        : value,
                    ),
                  }))
                }
              />
            </div>
            <div className="ac-channel-bottom">
              <AdminStatus tone={item.configured ? "green" : "orange"}>
                {item.configured
                  ? "连接状态 · 演示已配置"
                  : "连接状态 · 待配置"}
              </AdminStatus>
              <button
                className="ac-link-button"
                onClick={() => setChannel(item)}
              >
                <Settings2 size={14} />
                配置
              </button>
              <button className="ds-button" onClick={() => sendDemo(item)}>
                <Send size={13} />
                测试发送
              </button>
            </div>
          </section>
        ))}
      </div>
      <AdminPanel
        title="复习消息模板"
        className="ds-spaced-panel"
        action={<span className="ac-muted">变量占位符驱动内容填充</span>}
      >
        <div className="ac-template-grid">
          <div>
            <label className="ac-field-label" htmlFor="admin-template">
              模板内容
            </label>
            <textarea
              id="admin-template"
              className="ac-template-input"
              value={template}
              onChange={(event) => {
                setTemplate(event.target.value);
                setError("");
              }}
            />
            <div className="ac-template-variables">
              {Object.keys(templateValues).map((key) => (
                <button
                  key={key}
                  onClick={() =>
                    setTemplate((previous) => `${previous}\n{{${key}}}`)
                  }
                >{`{{${key}}}`}</button>
              ))}
            </div>
            {error && (
              <p className="ac-form-error" role="alert">
                {error}
              </p>
            )}
            <button
              className="ds-button primary"
              onClick={() => {
                if (unknown.length) {
                  setError(`请检查未知变量 ${unknown.join("、")}`);
                  return;
                }
                if (!template.trim()) {
                  setError("模板内容不能为空");
                  return;
                }
                setState((previous) => ({ ...previous, template }));
                notify("模板已在当前浏览器保存（前端演示）。");
              }}
            >
              <Check size={15} />
              保存模板演示
            </button>
          </div>
          <div className="ac-message-preview">
            <span>
              <Eye size={15} />
              消息效果预览 · 示例内容
            </span>
            <pre>{preview}</pre>
          </div>
        </div>
      </AdminPanel>
      <AdminPanel
        title="消息发送历史"
        className="ds-spaced-panel"
        action={
          <select
            aria-label="筛选消息渠道"
            value={historyChannel}
            onChange={(event) => setHistoryChannel(event.target.value)}
          >
            <option value="all">全部渠道</option>
            {state.channels.map((item) => (
              <option key={item.id} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
        }
      >
        <div className="ds-table-wrap">
          <table aria-label="消息发送历史">
            <thead>
              <tr>
                <th>渠道</th>
                <th>用户</th>
                <th>时间</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {history
                .filter(
                  (item) =>
                    historyChannel === "all" || item.channel === historyChannel,
                )
                .map((item) => (
                  <tr key={item.id}>
                    <td>{item.channel}</td>
                    <td>{item.user}</td>
                    <td>{item.time}</td>
                    <td>{item.status}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!history.some(
            (item) =>
              historyChannel === "all" || item.channel === historyChannel,
          ) && <div className="ds-empty">当前渠道暂无发送记录</div>}
        </div>
      </AdminPanel>
      {channel && (
        <AdminDialog
          title={`${channel.name}通知配置`}
          close={() => setChannel(null)}
        >
          <form
            className="ac-form"
            onSubmit={(event) => {
              event.preventDefault();
              setState((previous) => ({
                ...previous,
                channels: previous.channels.map((item) =>
                  item.id === channel.id ? { ...item, configured: true } : item,
                ),
              }));
              setChannel(null);
              notify("渠道演示状态已保存，输入的凭据已清空。");
            }}
          >
            <label>
              接收身份 / 地址
              <input
                aria-label="通知接收身份"
                required
                placeholder="演示用户、Chat ID 或邮箱地址"
              />
            </label>
            <label>
              Token / Webhook / 授权密钥
              <input
                aria-label="通知渠道密钥"
                type="password"
                autoComplete="off"
                placeholder="仅演示输入，关闭后清空"
                required
              />
            </label>
            <p className="ac-muted">
              正式接入时按用户保存接收身份并通过后端保护凭据。当前表单仅用于界面验收。
            </p>
            <div className="ac-form-footer">
              <button className="ds-button primary">保存渠道演示</button>
            </div>
          </form>
        </AdminDialog>
      )}
    </>
  );
}

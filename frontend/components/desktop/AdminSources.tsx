"use client";
import { useState } from "react";
import { createPreviewId } from "./preview-id";
import {
  BookOpen,
  Check,
  Database,
  FileText,
  FolderOpen,
  KeyRound,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { useAdminDemo } from "./AdminDemoProvider";
import { AdminDialog, AdminPanel, AdminStatus, AdminToggle } from "./AdminUi";
import type { SourceConfig } from "./admin-console-data";

export default function AdminSources() {
  const { state, setState, notify } = useAdminDemo();
  const [draft, setDraft] = useState<SourceConfig | null>(null);
  const [history, setHistory] = useState([
    {
      id: "sync-1",
      source: "Windows 内核笔记库",
      time: "11-13 19:42",
      result: "示例成功",
      pages: 3,
    },
    {
      id: "sync-2",
      source: "英语学习",
      time: "11-13 19:40",
      result: "示例部分失败",
      pages: 2,
    },
  ]);
  const [credentialOpen, setCredentialOpen] = useState(false);
  function simulateSync(source: SourceConfig) {
    setHistory((previous) => [
      {
        id: createPreviewId(),
        source: source.name,
        time: "本次演示",
        result: "演示完成 · 未读取 Notion",
        pages: 0,
      },
      ...previous,
    ]);
    notify("同步交互演示已完成，未调用 Notion API。");
  }
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>连接你的知识来源</h2>
          <p>以 Notion 为核心，保留章节状态、正文和来源位置。</p>
        </div>
        <button className="ds-button" onClick={() => setCredentialOpen(true)}>
          <KeyRound size={16} />
          API 授权配置
        </button>
      </div>
      <div className="ac-source-banner">
        <span className="ac-notion-symbol">N</span>
        <div>
          <h2>Notion</h2>
          <p>
            {state.sources.length} 个数据库 · 最近同步 11-13 19:42 · 示例快照
          </p>
        </div>
        <AdminStatus tone="green">连接状态 · 演示已配置</AdminStatus>
      </div>
      <div className="ac-source-grid">
        {state.sources.map((source) => (
          <AdminPanel
            title={source.name}
            key={source.id}
            action={<Database size={18} />}
          >
            <p className="ac-muted">
              所属用户 {source.owner} · {source.database}
            </p>
            <p className="ac-muted">
              最近结果 · {source.failed ? "示例部分失败" : "示例成功"}
            </p>
            <div className="ac-source-stats">
              <span>
                <small>成功次数</small>
                <strong>{source.success}</strong>
              </span>
              <span>
                <small>失败次数</small>
                <strong>{source.failed}</strong>
              </span>
              <span>
                <small>最近同步</small>
                <strong>{source.lastSync}</strong>
              </span>
            </div>
            <div className="ac-source-auto">
              <span>自动同步</span>
              <AdminToggle
                label={`${source.name}自动同步`}
                checked={source.automatic}
                onChange={() =>
                  setState((previous) => ({
                    ...previous,
                    sources: previous.sources.map((item) =>
                      item.id === source.id
                        ? { ...item, automatic: !item.automatic }
                        : item,
                    ),
                  }))
                }
              />
              <select
                aria-label={`${source.name}同步频率`}
                value={source.frequency}
                onChange={(event) => {
                  const frequency = event.target.value;
                  setState((previous) => ({
                    ...previous,
                    sources: previous.sources.map((item) =>
                      item.id === source.id ? { ...item, frequency } : item,
                    ),
                  }));
                }}
              >
                {[15, 30, 60, 120].map((minutes) => (
                  <option key={minutes} value={minutes}>
                    每 {minutes} 分钟
                  </option>
                ))}
              </select>
            </div>
            <div className="ac-card-actions">
              <button
                className="ds-button"
                onClick={() => setDraft({ ...source })}
              >
                <Settings2 size={14} />
                配置数据库
              </button>
              <button
                className="ds-button primary"
                onClick={() => simulateSync(source)}
              >
                <RefreshCw size={14} />
                手动同步演示
              </button>
            </div>
          </AdminPanel>
        ))}
      </div>
      <AdminPanel
        title="同步历史"
        className="ds-spaced-panel"
        action={<span className="ac-muted">全部为示例或本地演示记录</span>}
      >
        <div className="ds-table-wrap">
          <table aria-label="同步历史">
            <thead>
              <tr>
                <th>数据源</th>
                <th>时间</th>
                <th>结果</th>
                <th>示例页面数</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <tr key={item.id}>
                  <td>{item.source}</td>
                  <td>{item.time}</td>
                  <td>{item.result}</td>
                  <td>{item.pages}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </AdminPanel>
      <AdminPanel title="数据来源扩展" className="ds-spaced-panel">
        <div className="ac-future-sources">
          {[
            { name: "Obsidian", icon: BookOpen },
            { name: "本地 Markdown", icon: FolderOpen },
            { name: "PDF 文档", icon: FileText },
            { name: "Word 文档", icon: FileText },
            { name: "其他来源", icon: Database },
          ].map((item) => (
            <div key={item.name}>
              <item.icon size={22} />
              <strong>{item.name}</strong>
              <small>接口规划中</small>
            </div>
          ))}
        </div>
      </AdminPanel>
      {credentialOpen && (
        <AdminDialog
          title="Notion 授权配置"
          close={() => setCredentialOpen(false)}
        >
          <form
            className="ac-form"
            onSubmit={(event) => {
              event.preventDefault();
              setCredentialOpen(false);
              notify("授权表单演示已保存，密钥输入已清空，真实授权待接线。");
            }}
          >
            <label>
              Integration Token
              <input
                aria-label="Notion Integration Token"
                type="password"
                autoComplete="off"
                placeholder="仅演示输入，关闭后清空"
                required
              />
            </label>
            <p className="ac-muted">
              正式接入时，将由每位用户授权自己的知识库页面。当前为授权配置表单演示。
            </p>
            <div className="ac-form-footer">
              <button className="ds-button primary">保存授权演示</button>
            </div>
          </form>
        </AdminDialog>
      )}
      {draft && (
        <AdminDialog title="配置 Notion 数据库" close={() => setDraft(null)}>
          <form
            className="ac-form"
            onSubmit={(event) => {
              event.preventDefault();
              setState((previous) => ({
                ...previous,
                sources: previous.sources.map((item) =>
                  item.id === draft.id ? draft : item,
                ),
              }));
              setDraft(null);
              notify("数据库演示配置已保存。");
            }}
          >
            <label>
              数据源名称
              <input
                value={draft.name}
                required
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
              />
            </label>
            <label>
              数据库页面 / ID
              <input
                value={draft.database}
                required
                onChange={(event) =>
                  setDraft({ ...draft, database: event.target.value })
                }
              />
            </label>
            <p className="ac-muted">
              章节状态映射采用未开始、进行中、已完成。完成整章后进入知识汇总与复习编排。
            </p>
            <div className="ac-form-footer">
              <button className="ds-button primary">
                <Check size={15} />
                保存演示配置
              </button>
            </div>
          </form>
        </AdminDialog>
      )}
    </>
  );
}

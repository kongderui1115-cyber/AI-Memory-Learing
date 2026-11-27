"use client";
import { useState } from "react";
import { createPreviewId } from "./preview-id";
import {
  Check,
  KeyRound,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { useAdminDemo } from "./AdminDemoProvider";
import { AdminDialog, AdminPanel, AdminStatus, AdminToggle } from "./AdminUi";
import type { ModelConfig } from "./admin-console-data";

const purposes = ["知识提取", "章节总结", "答案评价", "学习助手"];
const providers = ["DeepSeek", "Kimi", "OpenAI", "Claude", "OpenAI 兼容"];
export default function AdminModels() {
  const { state, setState, notify } = useAdminDemo();
  const [draft, setDraft] = useState<ModelConfig | null>(null);
  const [secret, setSecret] = useState("");
  const [deleting, setDeleting] = useState<ModelConfig | null>(null);
  const [tested, setTested] = useState<Record<string, string>>({});
  function close() {
    setDraft(null);
    setSecret("");
  }
  function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const value = {
      ...draft,
      name: draft.name.trim(),
      configured: draft.configured || secret.trim().length > 0,
    };
    setState((previous) => ({
      ...previous,
      models: previous.models.some((item) => item.id === value.id)
        ? previous.models.map((item) => (item.id === value.id ? value : item))
        : [...previous.models, value],
    }));
    close();
    notify("已保存模型演示配置，API Key 输入已清空。");
  }
  function disableOrDelete(model: ModelConfig, remove = false) {
    const models = remove
      ? state.models.filter((item) => item.id !== model.id)
      : state.models.map((item) =>
          item.id === model.id ? { ...item, enabled: !item.enabled } : item,
        );
    const unavailable = !models.find((item) => item.id === model.id)?.enabled;
    const fallback = models.find((item) => item.enabled)?.id ?? "";
    setState((previous) => ({
      ...previous,
      models,
      defaultModel:
        unavailable && previous.defaultModel === model.id
          ? fallback
          : previous.defaultModel,
      uses: Object.fromEntries(
        Object.entries(previous.uses).map(([purpose, id]) => [
          purpose,
          unavailable && id === model.id ? fallback : id,
        ]),
      ),
    }));
    setDeleting(null);
    notify(
      remove
        ? "已移除该模型的本地演示配置。"
        : "已更新模型启用状态（前端演示）。",
    );
  }
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>模型供应商</h2>
          <p>按学习用途选择大模型，供应商配置可扩展。</p>
        </div>
        <button
          className="ds-button primary"
          onClick={() => {
            setSecret("");
            setDraft({
              id: createPreviewId(),
              name: "",
              provider: "OpenAI 兼容",
              baseUrl: "",
              model: "",
              enabled: true,
              configured: false,
              purposes: [],
            });
          }}
        >
          <Plus size={16} />
          添加模型供应商
        </button>
      </div>
      <div className="ac-model-grid">
        {state.models.map((model) => (
          <section className="ds-panel ac-model-card" key={model.id}>
            <div className="ac-card-top">
              <span className="ac-provider-symbol">
                <Sparkles size={22} />
              </span>
              <div>
                <h2>{model.name}</h2>
                <small>{model.provider}</small>
              </div>
              <AdminToggle
                label={`启用 ${model.name}`}
                checked={model.enabled}
                onChange={() => disableOrDelete(model)}
              />
            </div>
            <div className="ac-model-badges">
              <AdminStatus tone={model.configured ? "green" : "orange"}>
                {model.configured ? "已配置 · 示例" : "待配置"}
              </AdminStatus>
              {state.defaultModel === model.id && (
                <AdminStatus>默认模型</AdminStatus>
              )}
            </div>
            <dl>
              <div>
                <dt>模型名称</dt>
                <dd>{model.model}</dd>
              </div>
              <div>
                <dt>Base URL</dt>
                <dd title={model.baseUrl}>{model.baseUrl || "待配置"}</dd>
              </div>
              <div>
                <dt>API Key</dt>
                <dd>
                  <KeyRound size={12} />
                  {model.configured ? "•••••••• · 演示配置" : "尚未配置"}
                </dd>
              </div>
            </dl>
            <div className="ac-model-purposes">
              {model.purposes.length ? (
                model.purposes.map((value) => <span key={value}>{value}</span>)
              ) : (
                <span>尚未分配用途</span>
              )}
            </div>
            {tested[model.id] && (
              <p className="ac-inline-demo" role="status">
                {tested[model.id]}
              </p>
            )}
            <div className="ac-card-actions">
              <button
                className="ds-button"
                onClick={() => {
                  setSecret("");
                  setDraft({ ...model });
                }}
              >
                <Pencil size={14} />
                编辑
              </button>
              <button
                className="ds-button"
                onClick={() =>
                  setTested((previous) => ({
                    ...previous,
                    [model.id]: model.configured
                      ? "前端演示完成 · 真实连接尚待后端验证"
                      : "前端演示 · 请先补充 API Key 和模型配置",
                  }))
                }
              >
                <Zap size={14} />
                连接测试
              </button>
              <button
                className="ac-link-button"
                disabled={!model.enabled || state.defaultModel === model.id}
                onClick={() => {
                  setState((previous) => ({
                    ...previous,
                    defaultModel: model.id,
                  }));
                  notify("默认模型已更新（前端演示）。");
                }}
              >
                设为默认
              </button>
              <button
                aria-label={`删除 ${model.name}`}
                className="ac-delete"
                onClick={() => setDeleting(model)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </section>
        ))}
      </div>
      <AdminPanel title="模型用途配置" className="ds-spaced-panel">
        <div className="ac-use-grid">
          {purposes.map((purpose) => (
            <label key={purpose}>
              <span>{purpose}</span>
              <select
                aria-label={`${purpose}使用模型`}
                value={state.uses[purpose] ?? ""}
                onChange={(event) => {
                  const id = event.target.value;
                  setState((previous) => ({
                    ...previous,
                    uses: { ...previous.uses, [purpose]: id },
                  }));
                  notify("用途配置已在当前浏览器保存（演示）。");
                }}
              >
                <option value="">请选择模型</option>
                {state.models
                  .filter((model) => model.enabled)
                  .map((model) => (
                    <option value={model.id} key={model.id}>
                      {model.name}
                    </option>
                  ))}
              </select>
            </label>
          ))}
        </div>
      </AdminPanel>
      {draft && (
        <AdminDialog
          title={
            state.models.some((item) => item.id === draft.id)
              ? "编辑模型配置"
              : "添加模型供应商"
          }
          close={close}
        >
          <form className="ac-form" onSubmit={save}>
            <label>
              配置名称
              <input
                aria-label="模型配置名称"
                required
                value={draft.name}
                onChange={(event) =>
                  setDraft({ ...draft, name: event.target.value })
                }
              />
            </label>
            <div className="ac-form-columns">
              <label>
                供应商
                <select
                  value={draft.provider}
                  onChange={(event) =>
                    setDraft({ ...draft, provider: event.target.value })
                  }
                >
                  {providers.map((provider) => (
                    <option key={provider}>{provider}</option>
                  ))}
                </select>
              </label>
              <label>
                模型名称
                <input
                  aria-label="模型名称"
                  required
                  value={draft.model}
                  onChange={(event) =>
                    setDraft({ ...draft, model: event.target.value })
                  }
                />
              </label>
            </div>
            <label>
              Base URL
              <input
                type="url"
                aria-label="模型 Base URL"
                required
                value={draft.baseUrl}
                onChange={(event) =>
                  setDraft({ ...draft, baseUrl: event.target.value })
                }
                placeholder="https://api.example.com/v1"
              />
            </label>
            <label>
              API Key
              <input
                type="password"
                aria-label="模型 API Key"
                autoComplete="off"
                value={secret}
                onChange={(event) => setSecret(event.target.value)}
                placeholder={
                  draft.configured
                    ? "已配置演示状态，留空保留"
                    : "仅用于输入交互演示"
                }
              />
            </label>
            <p className="ac-muted">
              密钥输入仅在弹窗内暂存，保存后清空。此页面保存配置元数据与演示标记。
            </p>
            <fieldset>
              <legend>模型用途</legend>
              <div className="ac-checkboxes">
                {purposes.map((purpose) => (
                  <label key={purpose}>
                    <input
                      type="checkbox"
                      checked={draft.purposes.includes(purpose)}
                      onChange={(event) =>
                        setDraft({
                          ...draft,
                          purposes: event.target.checked
                            ? [...draft.purposes, purpose]
                            : draft.purposes.filter(
                                (value) => value !== purpose,
                              ),
                        })
                      }
                    />
                    {purpose}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="ac-form-footer">
              <button type="button" className="ds-button" onClick={close}>
                取消
              </button>
              <button className="ds-button primary">
                <Check size={15} />
                保存演示配置
              </button>
            </div>
          </form>
        </AdminDialog>
      )}
      {deleting && (
        <AdminDialog title="移除模型演示配置" close={() => setDeleting(null)}>
          <p className="ac-dialog-text">
            将从当前浏览器演示中移除“{deleting.name}
            ”。关联用途会切换至可用的演示模型。
          </p>
          <div className="ac-form-footer">
            <button className="ds-button" onClick={() => setDeleting(null)}>
              取消
            </button>
            <button
              className="ds-button ac-danger"
              onClick={() => disableOrDelete(deleting, true)}
            >
              确认移除
            </button>
          </div>
        </AdminDialog>
      )}
    </>
  );
}

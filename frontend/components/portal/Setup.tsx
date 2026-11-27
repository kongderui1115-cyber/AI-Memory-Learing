"use client";

import { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  LoaderCircle,
  Mail,
  RefreshCw,
  Send,
} from "lucide-react";
import { webApi } from "@/lib/workspace";
import type { DiscoveredSource, WorkspaceData } from "@/lib/workspace";

const stepNames = ["邮箱通知", "连接 Notion", "选择 AI 模型", "准备就绪"];
const statusNames = ["未开始", "进行中", "已完成"];
const targets = ["not_started", "in_progress", "completed"];

export default function Setup({
  data,
  reload,
  onboarding = false,
  onDone,
}: {
  data: WorkspaceData;
  reload: () => Promise<void>;
  onboarding?: boolean;
  onDone?: () => void;
}) {
  const [step, setStep] = useState(
    onboarding ? Math.min(data.profile.onboarding_step, 3) : 0,
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [recipient, setRecipient] = useState(
    data.profile.recipient_email || data.user.email,
  );
  const [time, setTime] = useState(data.profile.reminder_time);
  const [emailProvider, setEmailProvider] = useState(
    data.profile.email_settings.provider ||
      (
        {
          "qq.com": "qq",
          "foxmail.com": "qq",
          "163.com": "163",
          "gmail.com": "gmail",
          "outlook.com": "outlook",
          "hotmail.com": "outlook",
        } as Record<string, string>
      )[data.user.email.split("@")[1]] ||
      "qq",
  );
  const [smtpUser, setSmtpUser] = useState(
    data.profile.email_settings.username || data.user.email,
  );
  const [smtpPassword, setSmtpPassword] = useState("");
  const [enabled, setEnabled] = useState(
    data.profile.email_enabled || onboarding,
  );
  const [token, setToken] = useState("");
  const [query, setQuery] = useState("");
  const [discovered, setDiscovered] = useState<DiscoveredSource[]>([]);
  const [selected, setSelected] = useState<DiscoveredSource | null>(null);
  const [externalId, setExternalId] = useState(
    data.sources[0]?.external_source_id || "",
  );
  const [sourceType, setSourceType] = useState(
    data.sources[0]?.source_type || "database",
  );
  const [sourceName, setSourceName] = useState(
    data.sources[0]?.name || "我的学习笔记",
  );
  const [subject, setSubject] = useState(
    data.subjects?.find((s) => s.id === data.sources[0]?.subject_id)?.name ||
      "我的学习",
  );
  const [statusProperty, setStatusProperty] = useState(
    data.sources[0]?.status_property || "状态",
  );
  const [labels, setLabels] = useState(
    statusNames.map(
      (label, i) =>
        Object.keys(data.sources[0]?.status_mapping || {}).find(
          (k) => data.sources[0].status_mapping[k] === targets[i],
        ) || label,
    ),
  );
  const [modelProvider, setModelProvider] = useState(
    data.model?.base_url?.includes("moonshot")
      ? "kimi"
      : data.model?.provider || "deepseek",
  );
  const [modelName, setModelName] = useState(
    data.model?.model_name || "deepseek-chat",
  );
  const [modelKey, setModelKey] = useState("");
  const [consent, setConsent] = useState(data.profile.ai_billing_approved);
  const [baseUrl, setBaseUrl] = useState(data.model?.base_url || "");

  async function act(action: () => Promise<void>) {
    setError("");
    setMessage("");
    setPending(true);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败，请重试");
    } finally {
      setPending(false);
    }
  }
  function chooseSource(source: DiscoveredSource) {
    setSelected(source);
    setExternalId(source.id);
    setSourceType("data_source");
    setSourceName(source.name);
    const property =
      source.properties.find((p) => p.type === "status") ||
      source.properties.find((p) => p.type === "select");
    if (property) {
      setStatusProperty(property.name);
      const aliases = [
        ["未开始", "Not started", "To do"],
        ["进行中", "In progress"],
        ["已完成", "Done", "Completed"],
      ];
      setLabels(
        aliases.map(
          (names, i) =>
            property.options.find((o) =>
              names.some((n) => n.toLowerCase() === o.toLowerCase()),
            ) ||
            property.options[i] ||
            statusNames[i],
        ),
      );
    }
  }
  async function advance(next: number) {
    await reload();
    if (onboarding) {
      const current = await webApi<WorkspaceData>("/workspace/settings");
      await webApi("/workspace/profile", {
        method: "PUT",
        version: current.profile.version,
        body: {
          recipient_email: recipient,
          reminder_time: time,
          timezone: data.user.timezone,
          onboarding_step: next,
        },
      });
      await reload();
    }
    setStep(next);
  }
  async function saveCurrent() {
    if (step === 0) {
      const current = await webApi<WorkspaceData>("/workspace/settings");
      await webApi("/workspace/profile", {
        method: "PUT",
        version: current.profile.version,
        body: {
          recipient_email: recipient,
          reminder_time: time,
          timezone: data.user.timezone,
          onboarding_step: 0,
        },
      });
      const updated = await webApi<WorkspaceData>("/workspace/settings");
      await webApi("/workspace/email", {
        method: "PUT",
        version: updated.profile.version,
        body: {
          provider: emailProvider,
          username: smtpUser,
          password: smtpPassword || undefined,
          enabled,
        },
      });
      setSmtpPassword("");
    }
    if (step === 1) {
      if (!externalId.trim())
        throw new Error("请选择已授权资料库，或点击稍后配置");
      if (new Set(labels).size !== 3)
        throw new Error("三个学习阶段请分别选择对应状态");
      await webApi("/workspace/notion/connect", {
        method: "POST",
        body: {
          external_id: externalId,
          source_type: sourceType,
          name: sourceName,
          subject_name: subject,
          status_property: statusProperty,
          status_mapping: Object.fromEntries(
            labels.map((label, i) => [label, targets[i]]),
          ),
        },
      });
    }
    if (step === 2) {
      await webApi("/workspace/model", {
        method: "PUT",
        body: {
          provider: modelProvider,
          model_name: modelName,
          api_key: modelKey || undefined,
          billing_approved: consent,
          base_url: modelProvider === "openai_compatible" ? baseUrl : undefined,
        },
      });
      setModelKey("");
    }
    await reload();
    setMessage(step === 1 ? "资料库已保存，同步任务已创建。" : "设置已保存。");
    if (onboarding && step < 3) await advance(step + 1);
  }
  const propertyOptions =
    selected?.properties.find((p) => p.name === statusProperty)?.options || [];

  return (
    <section className="portal-setup">
      <nav className="portal-steps" aria-label="配置步骤">
        {stepNames.map((name, index) => (
          <button
            key={name}
            aria-current={step === index ? "step" : undefined}
            className={step === index ? "active" : ""}
            disabled={pending}
            onClick={() => setStep(index)}
          >
            <span>{index < step ? <Check size={16} /> : index + 1}</span>
            {name}
          </button>
        ))}
      </nav>
      <div className="portal-setup-body">
        <header>
          <span className="portal-eyebrow">
            {onboarding ? "打造你的学习空间" : "个人设置"}
          </span>
          <h2>{stepNames[step]}</h2>
          <p className="portal-muted">
            {
              [
                "把复习内容送到你常用的邮箱，包含知识正文、解析和原始笔记链接。",
                "保存 Token 后选择已授权资料库，系统会读取章节及学习状态。",
                "选择理解笔记的模型。你可以在需要时更换供应商和 API Key。",
                "配置会随账户保存，之后可以随时回到设置中调整。",
              ][step]
            }
          </p>
        </header>
        {step === 0 && (
          <div className="portal-form-grid">
            <label>
              接收复习邮件的邮箱
              <input
                type="email"
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                required
              />
            </label>
            <label>
              每日提醒时间
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
              <small>{data.user.timezone}</small>
            </label>
            <label>
              发信邮箱服务商
              <select
                value={emailProvider}
                onChange={(e) => setEmailProvider(e.target.value)}
              >
                <option value="qq">QQ 邮箱</option>
                <option value="163">网易 163 邮箱</option>
                <option value="gmail">Gmail</option>
                <option value="outlook">Outlook / Microsoft 365</option>
              </select>
            </label>
            <label>
              发件邮箱账号
              <input
                type="email"
                value={smtpUser}
                onChange={(e) => setSmtpUser(e.target.value)}
                autoComplete="off"
              />
            </label>
            <label className="portal-span">
              邮箱授权码 / SMTP 密码
              <input
                type="password"
                value={smtpPassword}
                onChange={(e) => setSmtpPassword(e.target.value)}
                autoComplete="new-password"
                placeholder={
                  data.smtp_configured
                    ? "已保存，留空保留原授权码"
                    : "输入邮箱授权码"
                }
              />
              <small>
                在邮箱设置中开启 SMTP 服务并获取授权码，服务器参数由系统填写。
              </small>
            </label>
            <label className="portal-check portal-span">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              启用每日邮件复习提醒
            </label>
            <div className="portal-span portal-inline">
              <button
                className="portal-secondary"
                disabled={
                  pending ||
                  !data.smtp_configured ||
                  !data.profile.email_enabled
                }
                onClick={() =>
                  act(async () => {
                    await webApi("/workspace/email/test", { method: "POST" });
                    await reload();
                    setMessage(
                      "测试邮件已加入发送队列，发送结果可在通知记录查看。",
                    );
                  })
                }
              >
                <Send size={16} />
                发送测试邮件
              </button>
              <small>先保存配置，再测试发送。</small>
            </div>
            <div className="portal-span portal-channel-list">
              {data.channels
                .filter((c) => c.id !== "smtp")
                .map((c) => (
                  <span key={c.id}>
                    {c.name}
                    <small>后续接入</small>
                  </span>
                ))}
            </div>
          </div>
        )}
        {step === 1 && (
          <div className="portal-form-grid">
            <label className="portal-span">
              Notion Token
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="new-password"
                placeholder={
                  data.notion_configured
                    ? "Token 已加密保存，输入新值可替换"
                    : "粘贴你的 Notion Token"
                }
              />
            </label>
            <div className="portal-inline portal-span">
              <button
                className="portal-secondary"
                disabled={pending || token.length < 10}
                onClick={() =>
                  act(async () => {
                    await webApi("/workspace/notion/token", {
                      method: "PUT",
                      body: { token },
                    });
                    setToken("");
                    await reload();
                    setMessage("Token 已加密保存，可以读取资料库列表。");
                  })
                }
              >
                保存 Token
              </button>
              <small>
                {data.notion_configured ? "凭据已保存" : "等待配置凭据"}
              </small>
            </div>
            <p className="portal-help portal-span">
              在 Notion 创建内部连接，并通过资料库右上角的连接菜单授予访问权限。
              <a
                href="https://app.notion.com/developers/connections"
                target="_blank"
                rel="noreferrer"
              >
                打开 Notion 开发者后台 ↗
              </a>
            </p>
            <div className="portal-inline portal-span">
              <input
                aria-label="搜索资料库"
                placeholder="按资料库标题搜索"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button
                className="portal-secondary"
                disabled={pending || !data.notion_configured}
                onClick={() =>
                  act(async () => {
                    const result = await webApi<{
                      items: DiscoveredSource[];
                      has_more: boolean;
                    }>(
                      "/workspace/notion/discover?q=" +
                        encodeURIComponent(query),
                    );
                    setDiscovered(result.items);
                    setMessage(
                      result.items.length
                        ? `读取到 ${result.items.length} 个已授权资料库`
                        : "没有找到资料库，请检查 Notion 连接的内容授权。",
                    );
                  })
                }
              >
                <RefreshCw size={16} />
                读取资料库
              </button>
            </div>
            {discovered.length > 0 && (
              <div className="portal-source-options portal-span">
                {discovered.map((source) => (
                  <button
                    key={source.id}
                    className={selected?.id === source.id ? "selected" : ""}
                    onClick={() => chooseSource(source)}
                  >
                    <BookIcon />
                    {source.name}
                    {selected?.id === source.id && <Check size={17} />}
                  </button>
                ))}
              </div>
            )}
            <label className="portal-span">
              资料库链接或 ID
              <input
                value={externalId}
                onChange={(e) => {
                  setExternalId(e.target.value);
                  setSourceType("database");
                }}
                placeholder="选择上方资料库，或粘贴 Notion 资料库链接"
              />
            </label>
            <label>
              资料库名称
              <input
                value={sourceName}
                onChange={(e) => setSourceName(e.target.value)}
                maxLength={120}
              />
            </label>
            <label>
              归属学科
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                maxLength={120}
                placeholder="例如英语、Windows 内核、数学"
              />
            </label>
            <label className="portal-span">
              学习状态属性
              {selected ? (
                <select
                  value={statusProperty}
                  onChange={(e) => setStatusProperty(e.target.value)}
                >
                  {selected.properties
                    .filter((p) => ["status", "select"].includes(p.type))
                    .map((p) => (
                      <option key={p.name}>{p.name}</option>
                    ))}
                </select>
              ) : (
                <input
                  value={statusProperty}
                  onChange={(e) => setStatusProperty(e.target.value)}
                />
              )}
            </label>
            <div className="portal-status-map portal-span">
              {statusNames.map((name, i) => (
                <label key={name}>
                  {name}
                  {propertyOptions.length ? (
                    <select
                      value={labels[i]}
                      onChange={(e) =>
                        setLabels(
                          labels.map((v, j) => (i === j ? e.target.value : v)),
                        )
                      }
                    >
                      {propertyOptions.map((option) => (
                        <option key={option}>{option}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={labels[i]}
                      onChange={(e) =>
                        setLabels(
                          labels.map((v, j) => (i === j ? e.target.value : v)),
                        )
                      }
                    />
                  )}
                </label>
              ))}
            </div>
            <p className="portal-help portal-span">
              未开始和进行中的章节持续同步。整章完成后，系统会安排知识提取与复习。
            </p>
          </div>
        )}
        {step === 2 && (
          <div className="portal-form-grid">
            <label>
              模型供应商
              <select
                value={modelProvider}
                onChange={(e) => {
                  setModelProvider(e.target.value);
                  setModelName(
                    e.target.value === "deepseek"
                      ? "deepseek-chat"
                      : e.target.value === "openai"
                        ? "gpt-4o-mini"
                        : "",
                  );
                }}
              >
                <option value="deepseek">DeepSeek</option>
                <option value="kimi">Kimi / Moonshot</option>
                <option value="openai">OpenAI</option>
                <option value="openai_compatible">其他兼容模型</option>
              </select>
            </label>
            <label>
              模型名称
              <input
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                placeholder="填写账户可用的模型名称"
              />
            </label>
            {modelProvider === "openai_compatible" && (
              <label className="portal-span">
                兼容模型 API 地址
                <input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="由管理员授权的兼容地址"
                />
              </label>
            )}
            <label className="portal-span">
              API Key
              <input
                type="password"
                value={modelKey}
                onChange={(e) => setModelKey(e.target.value)}
                autoComplete="new-password"
                placeholder={
                  data.model_key_configured
                    ? "已保存，留空保留原 Key"
                    : "输入模型 API Key"
                }
              />
            </label>
            <label className="portal-check portal-span">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              允许使用此模型处理我的笔记，并按供应商规则产生 API 费用
            </label>
            <p className="portal-help portal-span">
              AI 生成内容会关联原始笔记。你手动修订的知识点和卡片会被保留。
            </p>
          </div>
        )}
        {step === 3 && (
          <div className="portal-ready">
            <CheckCircle2 size={54} />
            <h3>你的学习空间已准备好</h3>
            <div>
              {[
                [
                  "邮箱通知",
                  data.smtp_configured && data.profile.email_enabled,
                ],
                ["Notion 资料库", data.sources.length > 0],
                [
                  "AI 模型",
                  data.model_key_configured && data.profile.ai_billing_approved,
                ],
              ].map(([title, configured]) => (
                <p key={String(title)}>
                  <span>{title}</span>
                  <strong>{configured ? "已配置" : "可稍后设置"}</strong>
                </p>
              ))}
            </div>
            <p className="portal-muted">
              新的笔记和复习进度会在学习主页中显示。
            </p>
          </div>
        )}
        {error && (
          <p className="portal-error" role="alert">
            {error}
          </p>
        )}
        {message && (
          <p className="portal-success" role="status">
            {message}
          </p>
        )}
        <footer className="portal-setup-actions">
          {step > 0 && (
            <button
              className="portal-secondary"
              disabled={pending}
              onClick={() => setStep(step - 1)}
            >
              <ArrowLeft size={16} />
              上一步
            </button>
          )}
          {onboarding && step < 3 && (
            <button
              className="portal-text-button"
              disabled={pending}
              onClick={() => act(() => advance(step + 1))}
            >
              稍后配置
            </button>
          )}
          <button
            className="portal-primary"
            disabled={pending}
            onClick={() =>
              act(async () => {
                if (step === 3) {
                  await webApi("/workspace/onboarding/complete", {
                    method: "POST",
                  });
                  await reload();
                  onDone?.();
                } else await saveCurrent();
              })
            }
          >
            {pending ? (
              <LoaderCircle className="portal-spin" size={17} />
            ) : (
              <>
                {step === 3
                  ? "进入学习空间"
                  : onboarding
                    ? "保存并继续"
                    : step === 1
                      ? "保存并同步"
                      : "保存设置"}
                <ArrowRight size={17} />
              </>
            )}
          </button>
        </footer>
      </div>
    </section>
  );
}

function BookIcon() {
  return <span className="portal-source-mark">N</span>;
}

"use client";
import { useState } from "react";
import { BrainCircuit, Check, RefreshCw } from "lucide-react";
import { useAdminDemo } from "./AdminDemoProvider";
import { AdminPanel, AdminStatus } from "./AdminUi";

export default function AdminMemory() {
  const { state, setState, notify } = useAdminDemo();
  const [intervals, setIntervals] = useState(state.intervals);
  const [retention, setRetention] = useState(state.retention);
  const [maxInterval, setMaxInterval] = useState(state.maxInterval);
  const [error, setError] = useState("");
  function saveIntervals(event: React.FormEvent) {
    event.preventDefault();
    const days = intervals
      .split(/[,，\s]+/)
      .filter(Boolean)
      .map(Number);
    if (
      !days.length ||
      days.some(
        (day, index) =>
          !Number.isFinite(day) ||
          day <= 0 ||
          (index > 0 && day <= days[index - 1]),
      )
    ) {
      setError("复习间隔须为递增的正数，单位为天。");
      return;
    }
    setError("");
    setState((previous) => ({ ...previous, intervals: days.join(", ") }));
    notify("艾宾浩斯间隔已保存为演示配置。");
  }
  return (
    <>
      <div className="ac-page-intro">
        <div>
          <h2>复习调度策略</h2>
          <p>章节完成后生成复习计划，评分与历史用于后续调度。</p>
        </div>
        <label className="ac-default-strategy">
          默认策略
          <select
            aria-label="默认记忆策略"
            value={state.defaultStrategy}
            onChange={(event) => {
              const defaultStrategy = event.target.value;
              setState((previous) => ({ ...previous, defaultStrategy }));
              notify("默认策略已更新（前端演示）。");
            }}
          >
            <option>FSRS</option>
            <option>艾宾浩斯</option>
          </select>
        </label>
      </div>
      <div className="ac-memory-grid">
        <AdminPanel
          title="艾宾浩斯固定间隔"
          action={<AdminStatus>固定复习阶段</AdminStatus>}
        >
          <div className="ac-memory-heading">
            <span className="ac-provider-symbol">
              <RefreshCw size={25} />
            </span>
            <p>按完成整章后的时间基点，编排固定间隔复习。</p>
          </div>
          <form className="ac-form" onSubmit={saveIntervals}>
            <label>
              复习间隔（天）
              <input
                aria-label="艾宾浩斯复习间隔"
                value={intervals}
                onChange={(event) => {
                  setIntervals(event.target.value);
                  setError("");
                }}
                placeholder="1, 2, 4, 7, 15, 30"
                required
              />
            </label>
            <p className="ac-muted">
              多个间隔使用逗号分隔。当前默认值沿用现有调度模块配置。
            </p>
            <div className="ac-interval-timeline">
              {state.intervals.split(",").map((day, index) => (
                <span key={index}>
                  <small>阶段 {index + 1}</small>
                  <strong>{day.trim()} 天</strong>
                </span>
              ))}
            </div>
            {error && (
              <p className="ac-form-error" role="alert">
                {error}
              </p>
            )}
            <div className="ac-form-footer">
              <button
                type="button"
                className="ds-button"
                onClick={() => setIntervals("1, 2, 4, 7, 15, 30")}
              >
                恢复默认输入
              </button>
              <button className="ds-button primary">
                <Check size={15} />
                保存固定间隔
              </button>
            </div>
          </form>
        </AdminPanel>
        <AdminPanel
          title="FSRS 自适应记忆"
          action={<AdminStatus tone="green">按评分调整</AdminStatus>}
        >
          <div className="ac-memory-heading">
            <span className="ac-provider-symbol purple">
              <BrainCircuit size={25} />
            </span>
            <p>根据真实回忆评分与历史状态，由后端计算下次复习时间。</p>
          </div>
          <form
            className="ac-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (
                !Number.isFinite(retention) ||
                retention <= 0 ||
                retention >= 100 ||
                !Number.isFinite(maxInterval) ||
                maxInterval < 1
              ) {
                notify("请填写有效的目标保持率和最大间隔。");
                return;
              }
              setState((previous) => ({ ...previous, retention, maxInterval }));
              notify("FSRS 演示配置已保存，实际调度待后端接线。");
            }}
          >
            <label>
              目标记忆保持率（%）
              <input
                aria-label="FSRS目标保持率"
                type="number"
                min="1"
                max="99.9"
                step="0.1"
                value={retention}
                onChange={(event) => setRetention(Number(event.target.value))}
                required
              />
            </label>
            <label>
              最大复习间隔（天）
              <input
                aria-label="FSRS最大间隔"
                type="number"
                min="1"
                value={maxInterval}
                onChange={(event) => setMaxInterval(Number(event.target.value))}
                required
              />
            </label>
            <div className="ac-rating-preview">
              {["忘记", "困难", "记得", "熟练"].map((label, index) => (
                <span className={`rating-${index}`} key={label}>
                  {label}
                </span>
              ))}
            </div>
            <p className="ac-muted">
              当前页面展示参数与评分入口，正式记忆状态、到期时间和算法版本由服务端管理。
            </p>
            <div className="ac-form-footer">
              <button className="ds-button primary">
                <Check size={15} />
                保存 FSRS 参数
              </button>
            </div>
          </form>
        </AdminPanel>
      </div>
      <AdminPanel title="章节完成后的复习流程" className="ds-spaced-panel">
        <div className="ac-memory-flow">
          {[
            "Notion 标记已完成",
            "汇总整章知识与解析",
            "生成复习卡片",
            "按用户策略编排",
            "评分后更新记忆",
          ].map((label, index) => (
            <div key={label}>
              <span>{index + 1}</span>
              <strong>{label}</strong>
            </div>
          ))}
        </div>
      </AdminPanel>
    </>
  );
}

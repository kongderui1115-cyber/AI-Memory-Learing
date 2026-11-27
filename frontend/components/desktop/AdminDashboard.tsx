"use client";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  Bell,
  BookOpen,
  Clock3,
  Database,
  Layers3,
  Sparkles,
  Users,
} from "lucide-react";
import { StudyTrend, Donut } from "./PreviewCharts";
import { previewWorkspace } from "./preview-data";
import { adminPreviewUsers } from "./admin-preview-data";
import { AdminPanel, AdminStatus } from "./AdminUi";
import { useAdminDemo } from "./AdminDemoProvider";

export default function AdminDashboard() {
  const { state } = useAdminDemo();
  const metrics = [
    {
      title: "知识点总数",
      value: "1,842",
      note: "3 位示例用户",
      icon: BookOpen,
      color: "blue",
    },
    {
      title: "学科总数",
      value: "8",
      note: "通用学科配置",
      icon: Layers3,
      color: "purple",
    },
    {
      title: "今日新增知识点",
      value: "72",
      note: "示例同步与提取",
      icon: Database,
      color: "cyan",
    },
    {
      title: "今日待复习",
      value: "13",
      note: "今日应复习 45 项",
      icon: Clock3,
      color: "orange",
    },
    {
      title: "今日已完成",
      value: "32",
      note: "完成率 71%",
      icon: Activity,
      color: "teal",
    },
    {
      title: "AI 模型调用",
      value: "128",
      note: "示例统计 · 未发起调用",
      icon: Sparkles,
      color: "purple",
    },
  ];
  return (
    <>
      <div className="ac-dashboard-banner">
        <div>
          <span>管理员工作空间</span>
          <h2>系统概况与学习进展</h2>
          <p>统一查看知识增长、复习任务与各服务的演示状态。</p>
        </div>
        <div>
          <AdminStatus tone="green">系统运行正常 · 示例</AdminStatus>
          <small>状态快照 2026-11-13 20:00 · Asia/Shanghai</small>
        </div>
      </div>
      <div className="ac-dashboard-metrics">
        {metrics.map((metric) => (
          <section className="ds-panel" key={metric.title}>
            <span className={`ds-subject-symbol ${metric.color}`}>
              <metric.icon size={20} />
            </span>
            <small>{metric.title}</small>
            <strong>{metric.value}</strong>
            <p>{metric.note}</p>
          </section>
        ))}
      </div>
      <div className="ac-status-grid">
        <AdminPanel title="Notion 同步">
          <span className="ac-service-icon">
            <Database size={19} />
          </span>
          <strong className="ac-service-value">11-13 19:42</strong>
          <p className="ac-muted">最近同步时间 · 示例</p>
          <Link href="/preview/admin/sources">
            {state.sources.length} 个数据库配置 <ArrowUpRight size={13} />
          </Link>
        </AdminPanel>
        <AdminPanel title="通知服务">
          <span className="ac-service-icon teal">
            <Bell size={19} />
          </span>
          <strong className="ac-service-value">
            {state.channels.filter((item) => item.enabled).length} 个渠道已启用
          </strong>
          <p className="ac-muted">示例配置就绪 · 实际投递待接线</p>
          <Link href="/preview/admin/notifications">
            查看通知管理 <ArrowUpRight size={13} />
          </Link>
        </AdminPanel>
        <AdminPanel title="后台任务">
          <span className="ac-service-icon purple">
            <Activity size={19} />
          </span>
          <strong className="ac-service-value">2 运行中 / 1 等待</strong>
          <p className="ac-muted">任务队列状态为示例</p>
          <div className="ac-job-tags">
            <span>知识提取 · 运行中</span>
            <span>复习计划 · 运行中</span>
            <span>通知队列 · 等待</span>
          </div>
        </AdminPanel>
      </div>
      <div className="ac-chart-grid">
        <AdminPanel
          title="学习与复习趋势"
          action={<span className="ac-muted">近14天 · 示例</span>}
        >
          <StudyTrend
            hours={previewWorkspace.trendHours}
            reviews={previewWorkspace.trendReviews}
            days={previewWorkspace.trendDays}
          />
        </AdminPanel>
        <AdminPanel title="用户知识量分布">
          <Donut
            total="1,842"
            caption="知识点"
            segments={adminPreviewUsers.map((user, index) => ({
              name: user.name,
              value: Math.round((user.knowledgeTotal / 1842) * 100),
              color: ["#4e80ff", "#a273fa", "#35c5c5"][index],
            }))}
          />
        </AdminPanel>
      </div>
      <div className="ac-bottom-grid">
        <AdminPanel
          title="最近系统活动"
          action={
            <Link className="ds-text-link" href="/preview/admin/security">
              查看日志 <ArrowUpRight size={13} />
            </Link>
          }
        >
          <div className="ac-activity-list">
            {state.securityEvents.slice(0, 5).map((event) => (
              <div key={event.id}>
                <span
                  className={`ac-activity-dot ${event.level === "信息" ? "" : "warning"}`}
                />
                <div>
                  <strong>
                    {event.actor} · {event.action}
                  </strong>
                  <p>{event.target}</p>
                </div>
                <small>{event.time.slice(11)}</small>
              </div>
            ))}
          </div>
        </AdminPanel>
        <AdminPanel title="用户学习概览" action={<Users size={18} />}>
          <div className="ac-user-summary">
            {adminPreviewUsers.map((user) => (
              <Link href="/preview/admin/users" key={user.id}>
                <span className="ds-mini-avatar">{user.name.slice(0, 1)}</span>
                <span>
                  <strong>{user.name}</strong>
                  <small>
                    今日完成 {user.todayCompleted} / {user.todayDue}
                  </small>
                </span>
                <b>
                  {Math.round((user.todayCompleted / user.todayDue) * 100)}%
                </b>
              </Link>
            ))}
          </div>
        </AdminPanel>
      </div>
    </>
  );
}

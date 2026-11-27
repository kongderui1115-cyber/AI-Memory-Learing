import { Activity, Bell, CalendarClock, Database, Gauge, LayoutDashboard, Settings, Sparkles } from "lucide-react";

export const navigation = [
  { id: "dashboard", label: "系统总览", icon: LayoutDashboard, group: "总览" },
  { id: "models", label: "AI 模型管理", icon: Sparkles, group: "配置" },
  { id: "sources", label: "数据源管理", icon: Database, group: "配置" },
  { id: "notifications", label: "通知管理", icon: Bell, group: "配置" },
  { id: "memory", label: "记忆策略", icon: Activity, group: "配置" },
  { id: "jobs", label: "任务调度", icon: CalendarClock, group: "运维" },
  { id: "monitoring", label: "系统监控", icon: Gauge, group: "运维" },
  { id: "settings", label: "系统设置", icon: Settings, group: "运维" },
] as const;

export type Section = (typeof navigation)[number]["id"];

export function sectionPath(section: Section, demo: boolean) {
  return (demo ? "/demo" : "") + (section === "dashboard" ? "" : "/" + section) || "/";
}

import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./desktop.css";
import "./admin-preview.css";
import "./admin-console.css";

export const metadata: Metadata = {
  title: "AI 学习记忆系统 · 桌面界面预览",
  description:
    "桌面学习仪表盘、章节进度、知识库与复习详情的交互预览。所有预览数据均为示例。",
  robots: { index: false, follow: false },
};

export default function PreviewLayout({ children }: { children: ReactNode }) {
  return children;
}

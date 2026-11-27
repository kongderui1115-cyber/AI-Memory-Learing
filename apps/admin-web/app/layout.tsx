import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "管理控制台 | AI Learning Memory OS",
  description: "AI Learning Memory OS 独立管理员工作台",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}

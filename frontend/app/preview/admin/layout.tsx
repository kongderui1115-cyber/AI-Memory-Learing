import type { ReactNode } from "react";
import AdminShell from "@/components/desktop/AdminShell";
export const metadata = { title: "AI Learning Memory OS · 管理员后台演示" };
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}

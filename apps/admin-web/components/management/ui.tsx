"use client";

import { Check, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import styles from "./management.module.css";

export type Feedback = { text: string; error: boolean };

export function Badge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={styles.badge} data-tone={tone}><i />{children}</span>;
}

export function Panel({ title, subtitle, action, children }: { title: string; subtitle?: string; action?: ReactNode; children?: ReactNode }) {
  return <section className={styles.panel}>
    <div className={styles.panelHead}><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>
    {children}
  </section>;
}

export function Message({ feedback }: { feedback: Feedback | null }) {
  if (!feedback) return null;
  return <div className={styles.message} data-error={feedback.error} role={feedback.error ? "alert" : "status"}>
    {feedback.error ? <X size={16} /> : <Check size={16} />}{feedback.text}
  </div>;
}

export function formatTime(value: string, includeYear = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: includeYear ? "numeric" : undefined, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(parsed);
}

export function Table({ columns, children }: { columns: string[]; children: ReactNode }) {
  return <div className={styles.tableViewport} tabIndex={0} role="region" aria-label="管理数据表">
    <table><thead><tr>{columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead><tbody>{children}</tbody></table>
  </div>;
}

export function Dialog({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog className={styles.dialog} data-wide={wide} ref={dialog} aria-labelledby={id} onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className={styles.dialogHead}><h2 id={id}>{title}</h2><button type="button" className={styles.iconButton} aria-label="关闭" onClick={onClose}><X size={18} /></button></div>
    {children}
  </dialog>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className={styles.field}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

export function FormFooter({ submit = "保存配置", busy, onClose }: { submit?: string; busy: boolean; onClose: () => void }) {
  return <div className={styles.formFooter}><button type="button" className={styles.secondary} onClick={onClose}>取消</button><button type="submit" className={styles.primary} disabled={busy}>{busy ? "处理中…" : submit}</button></div>;
}

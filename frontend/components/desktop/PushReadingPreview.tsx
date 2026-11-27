"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Bell,
  BookOpen,
  BrainCircuit,
  Check,
  ExternalLink,
  FileText,
  Sparkles,
} from "lucide-react";
import type { DesktopWorkspaceData } from "./preview-data";

export default function PushReadingPreview({
  data,
}: {
  data: DesktopWorkspaceData;
}) {
  const item = data.reviewItems[0];
  const [rating, setRating] = useState("");
  const [notice, setNotice] = useState("");
  return (
    <main className="desktop-os ds-push-screen">
      <header className="ds-push-header">
        <span className="ds-brand-mark">
          <BrainCircuit size={23} />
        </span>
        <div>
          <strong>AI 学习记忆系统</strong>
          <small>PushPlus · 复习内容详情</small>
        </div>
        <Bell size={19} />
      </header>
      <div className="ds-push-body">
        <div className="ds-push-preview-label">手机推送详情预览 · 示例内容</div>
        <div className="ds-push-meta">
          <span className="ds-status active">到时间复习了</span>
          <span>
            第 {item.stage} 次复习 · {item.strategy}
          </span>
        </div>
        <h1>{item.title}</h1>
        <p className="ds-push-subtitle">
          先给自己一点时间回忆，再对照知识点与解析。
        </p>
        <section className="ds-question">
          <span>回忆一下</span>
          <h3>{item.question}</h3>
        </section>
        <section className="ds-push-section">
          <h2>
            <BookOpen size={19} />
            知识点
          </h2>
          <p>{item.content}</p>
        </section>
        <section className="ds-push-section">
          <h2>
            <Sparkles size={19} />
            解析与理解
          </h2>
          <p>{item.explanation}</p>
        </section>
        <button
          className="ds-push-source"
          onClick={() =>
            setNotice(
              "此处展示示例来源。正式同步后可打开你有访问权限的 Notion 原页面。",
            )
          }
        >
          <FileText size={21} />
          <span>
            <strong>Notion 原页面</strong>
            <small>{item.source}</small>
          </span>
          <ExternalLink size={17} />
        </button>
        <section className="ds-push-rating">
          <h2>这次记得怎么样？</h2>
          <p>选择最接近本次回忆情况的一项。</p>
          <div>
            {["忘记", "困难", "记得", "熟练"].map((label, index) => (
              <button
                className={`rating-${index}`}
                key={label}
                aria-pressed={rating === label}
                onClick={() => {
                  setRating(label);
                  setNotice(
                    `预览中已选择“${label}”。正式接入后会记录复习历史并更新下次到期时间。`,
                  );
                }}
              >
                {rating === label && <Check size={14} />} {label}
              </button>
            ))}
          </div>
        </section>
        {notice && (
          <p className="ds-push-notice" role="status">
            {notice}
          </p>
        )}
        <footer className="ds-push-footer">
          <span>笔记 · 理解 · 记忆 · 成长</span>
          <Link href="/preview">
            电脑端学习空间 <ArrowUpRight size={13} />
          </Link>
        </footer>
      </div>
    </main>
  );
}

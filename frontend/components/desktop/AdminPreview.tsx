"use client";

import { useState } from "react";
import {
  BookOpen,
  CheckCheck,
  ChevronRight,
  Clock3,
  ExternalLink,
  FileText,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";
import type {
  AdminKnowledgePoint,
  AdminUserSnapshot,
} from "./admin-preview-data";

function KnowledgeDetails({ point }: { point: AdminKnowledgePoint }) {
  return (
    <section className="ds-admin-point-detail" aria-label="知识点详情">
      <span className="ds-admin-eyebrow">
        {point.subject} · {point.mastery}
      </span>
      <h3>{point.title}</h3>
      <div>
        <strong>知识点</strong>
        <p>{point.content}</p>
      </div>
      <div>
        <strong>解析与理解</strong>
        <p>{point.explanation}</p>
      </div>
      <div className="ds-admin-source">
        <FileText size={17} />
        <span>
          <strong>Notion 原页面</strong>
          <small>{point.source}</small>
        </span>
        {point.sourceUrl && (
          <a
            href={point.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="打开 Notion 原页面"
          >
            <ExternalLink size={17} />
          </a>
        )}
      </div>
    </section>
  );
}

export default function AdminPreview({
  users,
}: {
  users: AdminUserSnapshot[];
}) {
  const [selectedId, setSelectedId] = useState(users[0]?.id ?? "");
  const [userQuery, setUserQuery] = useState("");
  const [tab, setTab] = useState<"reviews" | "knowledge">("reviews");
  const [reviewFilter, setReviewFilter] = useState("全部记录");
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [subject, setSubject] = useState("all");
  const [pointId, setPointId] = useState("");
  const selected = users.find((user) => user.id === selectedId) ?? users[0];
  const point = selected?.knowledge.find((item) => item.id === pointId);
  const visibleUsers = users.filter((user) =>
    `${user.name} ${user.email}`
      .toLowerCase()
      .includes(userQuery.trim().toLowerCase()),
  );
  const due = users.reduce((sum, user) => sum + user.todayDue, 0);
  const completed = users.reduce((sum, user) => sum + user.todayCompleted, 0);
  const overdue = users.reduce((sum, user) => sum + user.overdue, 0);

  function selectUser(id: string, nextTab = tab) {
    setSelectedId(id);
    setTab(nextTab);
    setReviewFilter("全部记录");
    setKnowledgeQuery("");
    setSubject("all");
    setPointId("");
  }

  const filteredKnowledge =
    selected?.knowledge.filter(
      (item) =>
        (subject === "all" || item.subject === subject) &&
        `${item.title} ${item.content} ${item.source}`
          .toLowerCase()
          .includes(knowledgeQuery.trim().toLowerCase()),
    ) ?? [];
  const filteredReviews =
    selected?.reviews.filter(
      (item) => reviewFilter === "全部记录" || item.status === reviewFilter,
    ) ?? [];

  return (
    <div className="ds-admin-view">
      <div className="ds-page-heading">
        <div>
          <h1>用户复习与知识库</h1>
          <p>按用户查看复习进度、掌握情况与知识库内容。</p>
        </div>
        <span className="ds-preview-inline">角色切换仅作用于页面预览</span>
      </div>
      <div className="ds-admin-metrics">
        {[
          {
            label: "示例用户",
            value: users.length,
            icon: Users,
            color: "blue",
          },
          { label: "今日应复习", value: due, icon: Clock3, color: "purple" },
          {
            label: "今日已完成",
            value: completed,
            icon: CheckCheck,
            color: "teal",
          },
          {
            label: "逾期任务",
            value: overdue,
            icon: BookOpen,
            color: "orange",
          },
        ].map((metric) => (
          <section key={metric.label}>
            <span className={`ds-subject-symbol ${metric.color}`}>
              <metric.icon size={21} />
            </span>
            <div>
              <small>{metric.label}</small>
              <strong>{metric.value.toLocaleString("zh-CN")}</strong>
            </div>
          </section>
        ))}
      </div>
      <section className="ds-panel">
        <div className="ds-panel-heading">
          <h2>用户复习概览</h2>
          <label className="ds-admin-search">
            <Search size={15} />
            <input
              aria-label="搜索用户"
              placeholder="搜索用户姓名或邮箱"
              value={userQuery}
              onChange={(event) => setUserQuery(event.target.value)}
            />
          </label>
        </div>
        <div className="ds-table-wrap">
          <table aria-label="用户复习概览">
            <thead>
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>今日复习</th>
                <th>逾期</th>
                <th>知识库</th>
                <th>最近学习</th>
                <th>查看内容</th>
              </tr>
            </thead>
            <tbody>
              {visibleUsers.map((user) => (
                <tr
                  key={user.id}
                  className={
                    selected?.id === user.id ? "ds-admin-selected" : ""
                  }
                >
                  <td>
                    <span className="ds-table-user">
                      <span className="ds-mini-avatar">
                        {user.name.slice(0, 1).toUpperCase()}
                      </span>
                      <span>
                        <strong>{user.name}</strong>
                        <small>{user.email}</small>
                      </span>
                    </span>
                  </td>
                  <td>{user.role === "admin" ? "管理员" : "普通用户"}</td>
                  <td>
                    <span className="ds-admin-completion">
                      <strong>
                        {user.todayCompleted} / {user.todayDue}
                      </strong>
                      <progress
                        max={Math.max(1, user.todayDue)}
                        value={user.todayCompleted}
                        aria-label={`${user.name} 今日复习进度`}
                      />
                    </span>
                  </td>
                  <td>
                    <span
                      className={
                        user.overdue > 0 ? "ds-admin-overdue" : "ds-muted"
                      }
                    >
                      {user.overdue} 项
                    </span>
                  </td>
                  <td>
                    {user.knowledgeTotal.toLocaleString("zh-CN")} 个知识点
                  </td>
                  <td>{user.lastActive}</td>
                  <td>
                    <div className="ds-admin-row-actions">
                      <button onClick={() => selectUser(user.id, "reviews")}>
                        查看复习
                      </button>
                      <button onClick={() => selectUser(user.id, "knowledge")}>
                        查看知识库
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleUsers.length === 0 && (
            <div className="ds-empty">没有找到符合条件的用户</div>
          )}
        </div>
      </section>
      {selected ? (
        <section
          className="ds-panel ds-spaced-panel ds-admin-user-detail"
          aria-label="用户学习详情"
        >
          <div className="ds-panel-heading">
            <h2>用户学习详情</h2>
            <label className="ds-admin-user-picker">
              当前用户
              <select
                aria-label="选择用户"
                value={selected.id}
                onChange={(event) => selectUser(event.target.value)}
              >
                {users.map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="ds-admin-detail-heading">
            <span className="ds-mini-avatar">
              {selected.name.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <h3>{selected.name} 的学习空间</h3>
              <small>
                {selected.email} · {selected.subjects.join(" / ")}
              </small>
            </div>
            <span className="ds-status">示例数据</span>
          </div>
          <div className="ds-admin-user-stats">
            <div>
              <span>今日完成率</span>
              <strong>
                {selected.todayDue > 0
                  ? Math.round(
                      (selected.todayCompleted / selected.todayDue) * 100,
                    )
                  : 0}
                %
              </strong>
            </div>
            <div>
              <span>连续学习</span>
              <strong>{selected.streak} 天</strong>
            </div>
            <div>
              <span>记忆保持率</span>
              <strong>{selected.retention}%</strong>
            </div>
            <div>
              <span>知识点总数</span>
              <strong>{selected.knowledgeTotal.toLocaleString("zh-CN")}</strong>
            </div>
          </div>
          <div
            className="ds-admin-detail-tabs"
            role="tablist"
            aria-label="用户详情内容"
          >
            <button
              role="tab"
              aria-selected={tab === "reviews"}
              onClick={() => {
                setTab("reviews");
                setPointId("");
              }}
            >
              复习情况
            </button>
            <button
              role="tab"
              aria-selected={tab === "knowledge"}
              onClick={() => {
                setTab("knowledge");
                setPointId("");
              }}
            >
              知识库
            </button>
          </div>
          {tab === "reviews" ? (
            <div className="ds-admin-review-content">
              <div className="ds-admin-detail-toolbar">
                <span className="ds-muted">
                  复习记录预览样本 · {selected.reviews.length} 条
                </span>
                <select
                  aria-label="筛选复习状态"
                  value={reviewFilter}
                  onChange={(event) => {
                    setReviewFilter(event.target.value);
                    setPointId("");
                  }}
                >
                  {["全部记录", "待复习", "已完成", "已逾期"].map((status) => (
                    <option key={status}>{status}</option>
                  ))}
                </select>
              </div>
              <div className="ds-table-wrap">
                <table aria-label={`${selected.name} 的复习记录`}>
                  <thead>
                    <tr>
                      <th>知识点</th>
                      <th>状态</th>
                      <th>复习次数</th>
                      <th>本次掌握</th>
                      <th>最近完成</th>
                      <th>下次复习</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReviews.map((review) => {
                      const knowledge = selected.knowledge.find(
                        (item) => item.id === review.knowledgeId,
                      );
                      return (
                        <tr key={review.id}>
                          <td>
                            <button
                              className="ds-admin-review-title"
                              disabled={!knowledge}
                              onClick={() => setPointId(review.knowledgeId)}
                            >
                              {knowledge?.title ?? "知识点待加载"}
                              <ChevronRight size={13} />
                            </button>
                            <small className="ds-admin-table-subject">
                              {knowledge?.subject} · {review.strategy}
                            </small>
                          </td>
                          <td>
                            <span
                              className={`ds-status ${review.status === "已完成" ? "done" : review.status === "已逾期" ? "paused" : "active"}`}
                            >
                              {review.status}
                            </span>
                          </td>
                          <td>第 {review.reviewCount} 次</td>
                          <td>{review.rating ?? "待评分"}</td>
                          <td>{review.reviewedAt ?? "尚未完成"}</td>
                          <td>{review.nextDue}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {filteredReviews.length === 0 && (
                  <div className="ds-empty">当前状态下没有复习记录</div>
                )}
              </div>
            </div>
          ) : (
            <div>
              <div className="ds-admin-detail-toolbar">
                <label className="ds-admin-search">
                  <Search size={15} />
                  <input
                    aria-label="搜索当前用户知识库"
                    placeholder="搜索知识点、原文或来源"
                    value={knowledgeQuery}
                    onChange={(event) => {
                      setKnowledgeQuery(event.target.value);
                      setPointId("");
                    }}
                  />
                </label>
                <select
                  aria-label="筛选当前用户学科"
                  value={subject}
                  onChange={(event) => {
                    setSubject(event.target.value);
                    setPointId("");
                  }}
                >
                  <option value="all">全部学科</option>
                  {selected.subjects.map((name) => (
                    <option key={name}>{name}</option>
                  ))}
                </select>
              </div>
              <p className="ds-admin-sample-note">
                知识库预览样本 · 共展示 {filteredKnowledge.length} 个知识点
              </p>
              <div className="ds-admin-knowledge-grid">
                {filteredKnowledge.map((item) => (
                  <button
                    key={item.id}
                    aria-label={`查看知识点 ${item.title}`}
                    className={pointId === item.id ? "selected" : ""}
                    onClick={() => setPointId(item.id)}
                  >
                    <span className="ds-admin-eyebrow">
                      {item.subject} · {item.mastery}
                    </span>
                    <h3>{item.title}</h3>
                    <p>{item.content}</p>
                    <span className="ds-admin-knowledge-footer">
                      <span>
                        <FileText size={13} />
                        {item.source}
                      </span>
                      <ChevronRight size={16} />
                    </span>
                  </button>
                ))}
              </div>
              {filteredKnowledge.length === 0 && (
                <div className="ds-empty">
                  当前用户的知识库中没有符合条件的内容
                </div>
              )}
            </div>
          )}
          {point && <KnowledgeDetails point={point} />}
        </section>
      ) : (
        <section className="ds-panel ds-spaced-panel">
          <div className="ds-empty">暂无用户学习数据</div>
        </section>
      )}
      <p className="ds-admin-access-note">
        <ShieldCheck size={17} />
        正式管理访问将由后端校验管理员权限，并记录用户详情与知识库的访问审计。
      </p>
    </div>
  );
}

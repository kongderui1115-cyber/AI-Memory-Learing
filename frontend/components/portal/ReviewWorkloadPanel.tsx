"use client";

import { useEffect, useState } from "react";
import { webApi } from "@/lib/workspace";

type ReviewWorkload = {
    local_date: string;
    timezone: string;
    queued: number;
    due_unqueued: number;
    can_enqueue: number;
    daily_limit: number;
    estimated_seconds: number | null;
    sample_size: number;
    automatic_processing_enabled: boolean;
};

export function useReviewWorkload(enabled: boolean, refresh: object) {
    const [data, setData] = useState<ReviewWorkload | null>(null);
    const [error, setError] = useState("");
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        if (!enabled) return;
        let active = true;
        webApi<ReviewWorkload>("/workspace/review-workload").then(snapshot => {
            if (!active) return;
            setData(snapshot);
            setError("");
        }).catch(() => {
            if (!active) return;
            setError("暂时无法读取复习负荷。");
        });
        return () => { active = false; };
    }, [enabled, refresh, attempt]);
    return { data, error, retry: () => setAttempt(previous => previous + 1) };
}

export function ReviewWorkloadPanel({ data, error, retry }: ReturnType<typeof useReviewWorkload>) {
    const guidance = data && (data.can_enqueue > 0
        ? "点击「更新任务」把到期知识加入今天的复习。"
        : data.due_unqueued > 0
            ? "今天的批次暂时无法加入更多知识点。其余到期知识会保留。"
            : data.queued === 0
                ? "当前没有需要复习的知识点。"
                : null);
    return (
        <section className="lx-panel lx-review-workload" aria-label="今日复习负荷">
            <h2>今日复习负荷</h2>
            {error && <p role="alert">{error} <button type="button" onClick={retry}>重试</button></p>}
            {data ? (
                <>
                    <dl>
                        <div><dt>已排队待办</dt><dd>{data.queued} 项</dd></div>
                        <div><dt>已到期未排队</dt><dd>{data.due_unqueued} 项</dd></div>
                        <div><dt>今天可加入</dt><dd>{data.can_enqueue} 项</dd></div>
                        <div>
                            <dt>待办预计耗时</dt>
                            <dd>{data.estimated_seconds === null ? "样本不足"
                                : `约 ${Math.ceil(data.estimated_seconds / 60)} 分钟`}</dd>
                        </div>
                    </dl>
                    <p>用时估计基于近 30 天的个人复习记录（有效样本 {data.sample_size} 条）。</p>
                    {!data.automatic_processing_enabled && <p>自动后台已暂停，可手动更新本地复习任务。</p>}
                    {guidance && <p>{guidance}</p>}
                </>
            ) : !error && <p role="status">正在读取复习负荷…</p>}
        </section>
    );
}

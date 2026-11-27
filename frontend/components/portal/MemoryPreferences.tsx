"use client";

import { useState } from "react";
import { webApi } from "@/lib/workspace";
import type { PortalProfile } from "@/lib/workspace";

export default function MemoryPreferences({ profile, busy, save }: {
    profile: PortalProfile;
    busy: boolean;
    save: (action: () => Promise<void>) => Promise<void>;
}) {
    const [strategy, setStrategy] = useState(profile.review_preferences?.strategy ?? "fsrs");
    const [intervals, setIntervals] = useState(profile.review_preferences?.intervals_days?.join(", ") ?? "1, 2, 4, 7, 15, 30");
    return <section className="lx-panel" aria-label="记忆策略设置">
        <div className="lx-panel-heading"><h2>新知识的记忆策略</h2></div>
        <p className="lx-help">应用于新加入计划的知识。学科指定策略优先，已建立的复习计划保持原有节奏。</p>
        <form onSubmit={event => {
            event.preventDefault();
            const fields = new FormData(event.currentTarget);
            void save(async () => {
                await webApi("/workspace/memory-preferences", {
                    method: "PUT",
                    version: profile.version,
                    body: {
                        strategy, intervals_days: intervals.split(/[,，]/).map(value => Number(value.trim())),
                        learning_goal: fields.get("goal"), learning_preference: fields.get("preference"),
                    },
                });
            });
        }}>
            <label>记忆算法<select value={strategy} onChange={event => setStrategy(event.target.value === "ebbinghaus" ? "ebbinghaus" : "fsrs")}>
                <option value="fsrs">FSRS 动态间隔</option>
                <option value="ebbinghaus">艾宾浩斯固定间隔</option>
            </select></label>
            {strategy === "ebbinghaus" && <label>固定间隔（天，逗号分隔）
                <input required value={intervals} onChange={event => setIntervals(event.target.value)}/>
            </label>}
            <label>学习目标<input name="goal" maxLength={500} defaultValue={profile.review_preferences?.learning_goal}/></label>
            <label>学习偏好<input name="preference" maxLength={500} defaultValue={profile.review_preferences?.learning_preference}/></label>
            <button className="portal-secondary" disabled={busy}>保存记忆策略</button>
        </form>
    </section>;
}

'use client';

import { useState } from 'react';
import { AIProvidersPanel } from '@/components/settings/AIProvidersPanel';
import { NotionSyncPanel } from '@/components/settings/NotionSyncPanel';
import { NotificationChannelsPanel } from '@/components/settings/NotificationChannelsPanel';
import { SubjectStrategyPanel } from '@/components/settings/SubjectStrategyPanel';

const sections = [
  { id: 'notion', label: 'Notion 同步', component: NotionSyncPanel },
  { id: 'ai', label: 'AI 模型', component: AIProvidersPanel },
  { id: 'notifications', label: '消息通知', component: NotificationChannelsPanel },
  { id: 'subjects', label: '学科策略', component: SubjectStrategyPanel },
];

export default function SettingsPage() {
  const [active, setActive] = useState(sections[0]);
  const Panel = active.component;
  return (
    <div className="page">
      <header className="page-head"><h1 className="page-title">设置</h1></header>
      <nav className="tabs" aria-label="设置分类">
        {sections.map((section) => (
          <button key={section.id} type="button"
            className={`tab-btn ${active.id === section.id ? 'tab-btn--active' : ''}`}
            aria-current={active.id === section.id ? 'page' : undefined}
            onClick={() => setActive(section)}>{section.label}</button>
        ))}
      </nav>
      <Panel key={active.id} />
    </div>
  );
}
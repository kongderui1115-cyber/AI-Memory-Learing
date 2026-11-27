'use client';

/** 知识管理入口：知识点 / 学科 两个标签页，共用一次真实的 GET /subjects。 */

import { useState } from 'react';
import { useSubjects } from '@/lib/hooks';
import { KnowledgeList } from '@/components/knowledge/KnowledgeList';
import { SubjectManager } from '@/components/knowledge/SubjectManager';

export default function KnowledgePage() {
  const [tab, setTab] = useState<'points' | 'subjects'>('points');
  const subjects = useSubjects();
  const subjectItems = subjects.state.status === 'success' ? subjects.state.data.items : [];

  return (
    <div className="page">
      <header className="page-head">
        <h1 className="page-title">知识管理</h1>
        <p className="page-sub">知识点、学科与标签 · 列表 / 详情 / 编辑全部读写真实接口</p>
      </header>

      <div className="tabs" role="tablist" aria-label="知识管理分类">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'points'}
          className={`tab-btn ${tab === 'points' ? 'tab-btn--active' : ''}`}
          onClick={() => setTab('points')}
        >
          知识点
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'subjects'}
          className={`tab-btn ${tab === 'subjects' ? 'tab-btn--active' : ''}`}
          onClick={() => setTab('subjects')}
        >
          学科
        </button>
      </div>

      {tab === 'points' ? (
        <KnowledgeList
          subjects={subjectItems}
          subjectMap={subjects.map}
          subjectsFailed={subjects.state.status === 'error'}
        />
      ) : (
        <SubjectManager state={subjects.state} reload={subjects.reload} />
      )}
    </div>
  );
}

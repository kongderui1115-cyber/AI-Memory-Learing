/** 枚举值 → 中文文案映射（UI 全中文，不把英文枚举直接暴露给用户）。 */

import type {
  AICallStatus,
  AIProviderType,
  BatchStatus,
  DeliveryStatus,
  KnowledgePointStatus,
  NotificationChannelType,
  NotificationJobStatus,
  NotionSourceType,
  QuestionType,
  ReviewRating,
  RunStatus,
  ScheduleStrategy,
  SyncTriggerType,
  TaskStatus,
} from '@/types/api';

export const RATING_ORDER: ReviewRating[] = ['again', 'hard', 'good', 'easy'];

/** 掌握程度评分，与 FSRS 的 again/hard/good/easy 对齐（FR-09）。 */
export const RATING_LABELS: Record<ReviewRating, { label: string; hint: string }> = {
  again: { label: '重来', hint: '完全没想起来，需要重新学习' },
  hard: { label: '困难', hint: '想起来了，但很吃力' },
  good: { label: '良好', hint: '基本掌握，稍有迟疑' },
  easy: { label: '轻松', hint: '非常熟练，毫不费力' },
};

export const KNOWLEDGE_STATUS_LABELS: Record<KnowledgePointStatus, string> = {
  draft: '草稿',
  active: '已激活',
  archived: '已归档',
  merged: '已合并',
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: '待复习',
  in_progress: '进行中',
  completed: '已完成',
  skipped: '已跳过',
  cancelled: '已取消',
};

export const BATCH_STATUS_LABELS: Record<BatchStatus, string> = {
  pending: '待生成',
  ready: '已就绪',
  completed: '已完成',
  cancelled: '已取消',
};

export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  qa: '问答题',
  cloze: '填空题',
  multiple_choice: '选择题',
  short_explanation: '简答 / 解释',
};

export const STRATEGY_LABELS: Record<ScheduleStrategy, string> = {
  ebbinghaus: '艾宾浩斯固定间隔',
  fsrs: 'FSRS 自适应',
};

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  pending: '等待中',
  running: '进行中',
  succeeded: '成功',
  failed: '失败',
  partial: '部分成功',
  cancelled: '已取消',
};

export const DIFFICULTY_LABELS = ['', '入门', '基础', '进阶', '较难', '困难'] as const;

/** 难度 1..5 → 星级字符串。 */
export function difficultyStars(difficulty: number): string {
  const n = Math.min(5, Math.max(0, Math.round(difficulty)));
  return '★'.repeat(n) + '☆'.repeat(5 - n);
}

/** 状态标签对应的样式类名后缀。 */
export function statusTone(status: KnowledgePointStatus): string {
  switch (status) {
    case 'active': return 'ok';
    case 'archived': return 'muted';
    case 'merged': return 'warn';
    default: return 'info';
  }
}

export function taskStatusTone(status: TaskStatus): string {
  switch (status) {
    case 'completed': return 'ok';
    case 'in_progress': return 'info';
    case 'skipped':
    case 'cancelled': return 'muted';
    default: return 'warn';
  }
}

// ---------------------------------------------------------------------------
// 设置页 / 统计页补充文案（FE-03 / FE-06 / FE-07）
// ---------------------------------------------------------------------------

/** 通知渠道类型（FR-07 / FR-08）。 */
export const CHANNEL_TYPE_LABELS: Record<NotificationChannelType, string> = {
  wecom_app: '企业微信应用消息',
  wechat_official_account: '微信服务号',
  third_party_push: '第三方微信推送',
  wecom_webhook: '企业微信群机器人',
  dingtalk_webhook: '钉钉群机器人',
  dingtalk_app: '钉钉应用消息',
  smtp: '邮件（SMTP）',
};

export const AI_PROVIDER_LABELS: Record<AIProviderType, string> = {
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  openai_compatible: 'OpenAI 兼容协议',
};

export const AI_CALL_STATUS_LABELS: Record<AICallStatus, string> = {
  pending: '等待中',
  running: '进行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
};

export function aiCallStatusTone(status: AICallStatus): string {
  switch (status) {
    case 'succeeded': return 'ok';
    case 'failed': return 'danger';
    case 'running': return 'info';
    case 'cancelled': return 'muted';
    default: return 'warn';
  }
}

export const SYNC_TRIGGER_LABELS: Record<SyncTriggerType, string> = {
  manual: '手动触发',
  scheduled: '定时触发',
};

export const NOTION_SOURCE_TYPE_LABELS: Record<NotionSourceType, string> = {
  database: '数据库',
  page_tree: '页面树',
};

export const NOTIFICATION_JOB_STATUS_LABELS: Record<NotificationJobStatus, string> = {
  pending: '等待中',
  processing: '处理中',
  sent: '已发送',
  failed: '失败',
  cancelled: '已取消',
};

export function notificationJobStatusTone(status: NotificationJobStatus): string {
  switch (status) {
    case 'sent': return 'ok';
    case 'failed': return 'danger';
    case 'processing': return 'info';
    case 'cancelled': return 'muted';
    default: return 'warn';
  }
}

export const DELIVERY_STATUS_LABELS: Record<DeliveryStatus, string> = {
  sending: '发送中',
  sent: '已送达',
  failed: '失败',
};

export function runStatusTone(status: RunStatus): string {
  switch (status) {
    case 'succeeded': return 'ok';
    case 'failed': return 'danger';
    case 'partial': return 'warn';
    case 'running': return 'info';
    case 'cancelled': return 'muted';
    default: return 'muted';
  }
}

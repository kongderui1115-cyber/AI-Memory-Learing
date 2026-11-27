export type AdminMode = "live" | "demo";
export type DateRange = { from: string; to: string };
export type Resource<T> = {
  source: "live" | "demo" | "unavailable";
  data: T | null;
  message?: string;
};
export type DashboardSummary = {
  knowledgePoints: number | null;
  subjects: number | null;
  todayNew: number | null;
  todayDue: number | null;
  todayCompleted: number | null;
  aiCalls: number | null;
  asOf: string;
  timezone: string;
};
export type LearningDay = {
  date: string;
  knowledge: number;
  studyMinutes: number;
  reviews: number;
  completionRate: number | null;
  assigned?: number;
  completed?: number;
};
export type RetentionPoint = {
  stage: string;
  subject: string;
  predicted: number | null;
  observed: number | null;
  sampleSize: number | null;
  subjectId?: string | null;
  predictionSampleSize?: number;
  predictionVersions?: string[];
};
export type SubjectMastery = {
  id: string;
  name: string;
  knowledge: number;
  completionRate: number | null;
  mastery: number | null;
  weak: number | null;
  recallSamples?: number;
};
export type AiAnalytics = {
  days: { date: string; calls: number; tokens: number | null; cost: number | null; errors: number; terminalCalls?: number; tokenSamples?: number }[];
  models: { name: string; value: number }[];
  tasks: { name: string; value: number }[];
  currency: string;
};
export type WorkflowCounts = {
  imported_versions: number;
  generated_points: number;
  sync_queued: number;
  extraction_queued: number;
  extraction_blocked: number;
  notification_queued: number;
};
export type SystemResourcePoint = {
  cpu: number | null;
  memory: number | null;
  disk: number | null;
  latencyMs: number | null;
  requests: number;
  errors: number;
};
export type SystemResources = SystemResourcePoint & {
  windowMinutes?: number;
  days: ({ date: string } & SystemResourcePoint)[];
};
export type JobAnalytics = {
  kinds: { key?: string; name: string; success: number; failure: number; partial?: number; averageMs: number | null; durationSamples?: number }[];
  days: { date: string; success: number; failure: number; partial?: number; averageMs: number | null; durationSamples?: number }[];
  chapterStatus?: Record<string, number>;
};
export type Severity = "info" | "warning" | "high";
export type ActivityEvent = {
  id: string;
  time: string;
  label: string;
  detail: string;
  severity: Severity;
};
export type SystemHealth = {
  status: "ready" | "unavailable";
  database: "ready" | "unavailable";
  migration: string | null;
  checkedAt: string;
};
export type DashboardData = {
  workflow?: WorkflowCounts;
  window?: DateRange & { timezone: string };
  summary: Resource<DashboardSummary>;
  learning: Resource<LearningDay[]>;
  retention: Resource<RetentionPoint[]>;
  subjects: Resource<SubjectMastery[]>;
  ai: Resource<AiAnalytics>;
  resources: Resource<SystemResources>;
  jobs: Resource<JobAnalytics>;
  activity: Resource<ActivityEvent[]>;
  health: Resource<SystemHealth>;
};

export type ManagementSection =
  | "models"
  | "sources"
  | "notifications"
  | "memory"
  | "jobs"
  | "monitoring"
  | "settings";
export type ManagementRecord = {
  id: string;
  name: string;
  detail: string;
  status: "ok" | "paused" | "failed" | "queued" | "planned" | "running";
  updatedAt: string;
  meta?: Record<string, string>;
};
export type ManagementInput = Omit<ManagementRecord, "id" | "updatedAt">;
export type Page<T> = { items: T[]; next_cursor: string | null; has_more: boolean };
export type AuditFilters = {
  limit?: number;
  severity?: Severity;
  user_id?: string;
  action?: string;
  cursor?: string;
  from?: string;
  to?: string;
};
export type AuditEvent = {
  id: string;
  actor_label: string;
  action: string;
  resource: string;
  outcome: string;
  severity: Severity;
  created_at: string;
  actor_id: string | null;
  target_user_id: string | null;
  request_id: string | null;
  ip_address?: string | null;
};
export type User = {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  version: number;
};
export type AdminUser = User & { role: "admin" };
export type UserCreate = { email: string; display_name: string; password: string; timezone: string };
export type UserUpdate = { display_name: string; is_active: boolean };
export type PageFilters = { limit?: number; cursor?: string };
export type LearnerOverview = {
  user: User;
  local_date: string;
  knowledge_count: number;
  chapter_count: number;
  today_completed: number;
  today_remaining: number;
  overdue: number;
};
export type LearnerKnowledge = {
  id: string;
  title: string;
  body: string;
  summary: string;
  subject_id: string;
  status: string;
  difficulty: number;
  updated_at: string;
  created_at: string;
  source_url: string | null;
  chapter_id: string | null;
};
export type LearnerReview = {
  id: string;
  knowledge_title: string;
  knowledge_point_id: string;
  subject_id: string | null;
  strategy: string;
  rating: string;
  duration_seconds: number;
  reviewed_at: string;
};
export type AdminSession = {
  id: string;
  user_id: string;
  email: string;
  display_name: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  logged_out_at: string | null;
  ip_address: string;
  user_agent: string;
  online: boolean;
};
export type PasswordInput = { current_password: string; new_password: string };
export type ResultMessage = { message: string };

export interface AdminClient {
  readonly mode: AdminMode;
  readonly operations: AdminOperations | null;
  login(email: string, password: string): Promise<AdminUser>;
  session(): Promise<AdminUser>;
  logout(): Promise<void>;
  changePassword(input: PasswordInput): Promise<void>;
  dashboard(range?: DateRange): Promise<DashboardData>;
  jobAnalytics(range?: DateRange): Promise<Resource<JobAnalytics>>;
  collection(section: ManagementSection): Promise<Resource<ManagementRecord[]>>;
  saveRecord(section: ManagementSection, input: ManagementInput, id?: string): Promise<Resource<ManagementRecord>>;
  deleteRecord(section: ManagementSection, id: string): Promise<Resource<null>>;
  runAction(section: ManagementSection, id: string, action: string): Promise<Resource<ResultMessage>>;
  audit(filters?: AuditFilters): Promise<Resource<Page<AuditEvent>>>;
  users(filters?: PageFilters & { q?: string }): Promise<Resource<Page<User>>>;
  createUser(input: UserCreate, key: string): Promise<User>;
  updateUser(userId: string, version: number, input: UserUpdate): Promise<User>;
  userOverview(userId: string): Promise<Resource<LearnerOverview>>;
  userKnowledge(userId: string, filters?: PageFilters): Promise<Resource<Page<LearnerKnowledge>>>;
  userHistory(userId: string, filters?: PageFilters): Promise<Resource<Page<LearnerReview>>>;
  sessions(filters?: { limit?: number; cursor?: string; user_id?: string; online_only?: boolean; from?: string; to?: string }): Promise<Resource<Page<AdminSession>>>;
  health(): Promise<Resource<SystemHealth>>;
}
import type { AdminOperations } from "./operations";


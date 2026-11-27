import type { AiAnalytics, Page, PageFilters, Resource } from "./types";

export type OwnerFilter = PageFilters & { user_id?: string };
export type Provider = {
  id: string;
  user_id: string;
  user_name: string;
  name: string;
  provider: string;
  model_name: string;
  endpoint_host: string | null;
  is_enabled: boolean;
  is_default: boolean;
  version: number;
  key_configured: boolean;
  user_billing_approved: boolean;
  global_billing_approved: boolean;
  configuration_status: string;
  connection_tested: false;
};

export type ProviderPatch = Partial<Pick<Provider, "is_enabled" | "is_default">>;
export type Strategy = "fsrs" | "ebbinghaus";
export type Rating = "again" | "hard" | "good" | "easy";
export type PolicyParameters = { strategy: Strategy; intervals_days: number[]; target_retention: number };
export type Policy = PolicyParameters & {
  id: string;
  user_id: string;
  user_name: string;
  subject_id: string;
  subject_name: string;
  version: number;
  is_active: boolean;
};
export type PolicyPage = Page<Policy> & { defaults: PolicyParameters };
export type SimulationInput = { strategy: Strategy; intervals_days?: number[]; target_retention?: number; ratings?: Rating[] };
export type Simulation = {
  strategy: Strategy;
  algorithm_version: string;
  steps: {
    review_count: number;
    rating: Rating;
    reviewed_at: string;
    due_at: string;
    interval_days: number;
    stability: number | null;
    difficulty: number | null;
    retrievability: number | null;
  }[];
  simulation: true;
};

export type Source = {
  id: string;
  user_id: string;
  owner_name: string;
  name: string;
  source_type: string;
  external_source_id: string;
  integration_name: string;
  is_enabled: boolean;
  integration_enabled: boolean;
  credential_configured: boolean;
  sync_interval_minutes: number;
  next_sync_at: string | null;
  last_synced_at: string | null;
  last_status: string | null;
  items_imported: number | null;
  items_failed: number | null;
};
export type SourceRun = {
  id: string;
  source_id: string;
  user_id: string;
  trigger_type: string;
  status: string;
  items_seen: number;
  items_imported: number;
  items_failed: number;
  attempt: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  next_retry_at: string | null;
  error_code: string | null;
};
export type Channel = {
  id: string;
  user_id: string;
  owner_name: string;
  name: string;
  channel_type: string;
  is_enabled: boolean;
  is_default: boolean;
  credential_configured: boolean;
  last_status: string | null;
  last_attempted_at: string | null;
};
export type Delivery = {
  id: string;
  job_id: string;
  channel_id: string;
  channel_name: string;
  channel_type: string;
  user_id: string;
  owner_name: string;
  purpose: string;
  status: string;
  attempt_no: number;
  attempted_at: string;
  duration_ms: number | null;
  error_code: string | null;
  provider_accepted: boolean | null;
  final_delivery: boolean | string | null;
};
export type Job = {
  id: string;
  user_id: string;
  owner_name: string;
  kind: string;
  name: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  attempt: number | null;
  error_code: string | null;
  next_attempt_at: string | null;
};
export type Telemetry = {
  sampled_at: string;
  window_minutes: number;
  cpu: number | null;
  memory: number | null;
  disk: number | null;
  latency_ms: number | null;
  p95_latency_ms: number | null;
  requests: number;
  errors: number;
  buckets: { date: string; requests: number; errors: number; latency_ms: number | null }[];
};
export type SystemInfo = {
  version: string;
  started_at: string;
  background_tasks_enabled: boolean;
  worker: "running" | "paused" | "unavailable";
  redis: "not_configured";
  backups_enabled: boolean;
};
export type Backup = { id: string; filename: string; created_at: string; size_bytes: number };
export type BackupList = { enabled: boolean; items: Backup[] };

export interface AdminOperations {
  providers(filter?: OwnerFilter): Promise<Page<Provider>>;
  providerReadiness(id: string): Promise<Provider>;
  updateProvider(id: string, version: number, patch: ProviderPatch): Promise<Provider>;
  aiUsage(): Promise<Resource<AiAnalytics>>;
  policies(filter?: OwnerFilter): Promise<PolicyPage>;
  updatePolicy(id: string, version: number, patch: Partial<PolicyParameters>): Promise<Policy>;
  simulate(input: SimulationInput): Promise<Simulation>;
  sources(filter?: OwnerFilter): Promise<Page<Source>>;
  sourceRuns(id: string, filter?: PageFilters): Promise<Page<SourceRun>>;
  queueSource(id: string, key: string): Promise<SourceRun>;
  channels(filter?: OwnerFilter): Promise<Page<Channel>>;
  deliveries(filter?: OwnerFilter & { channel_id?: string; status?: string }): Promise<Page<Delivery>>;
  jobs(filter?: OwnerFilter & { kind?: string; status?: string }): Promise<Page<Job>>;
  telemetry(minutes?: number): Promise<Telemetry>;
  systemInfo(): Promise<SystemInfo>;
  backups(): Promise<BackupList>;
  createBackup(key: string): Promise<Backup>;
}

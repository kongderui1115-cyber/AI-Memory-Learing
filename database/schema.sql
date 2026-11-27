BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial_schema

CREATE EXTENSION IF NOT EXISTS citext;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    email CITEXT NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    password_hash TEXT NOT NULL, 
    timezone VARCHAR(64) DEFAULT 'Asia/Shanghai' NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_users PRIMARY KEY (id), 
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE subjects (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    parent_id UUID, 
    slug VARCHAR(80) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description TEXT, 
    language_code VARCHAR(16) DEFAULT 'zh-CN' NOT NULL, 
    tags JSONB DEFAULT '[]'::jsonb NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_subjects PRIMARY KEY (id), 
    CONSTRAINT uq_subjects_user_id_slug UNIQUE (user_id, slug), 
    CONSTRAINT fk_subjects_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_subjects_parent_id_subjects FOREIGN KEY(parent_id) REFERENCES subjects (id) ON DELETE RESTRICT
);

CREATE TABLE subject_strategies (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    subject_id UUID NOT NULL, 
    extraction_prompt TEXT NOT NULL, 
    question_type_preferences JSONB DEFAULT '[]'::jsonb NOT NULL, 
    glossary JSONB DEFAULT '{}'::jsonb NOT NULL, 
    scheduler_overrides JSONB DEFAULT '{}'::jsonb NOT NULL, 
    notification_template_overrides JSONB DEFAULT '{}'::jsonb NOT NULL, 
    prompt_version VARCHAR(40) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_subject_strategies PRIMARY KEY (id), 
    CONSTRAINT fk_subject_strategies_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_subject_strategies_subject_id_subjects FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);

CREATE TABLE notion_integrations (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    credential_ref VARCHAR(160) NOT NULL, 
    api_version VARCHAR(20) DEFAULT '2022-06-28' NOT NULL, 
    is_enabled BOOLEAN DEFAULT true NOT NULL, 
    last_validated_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notion_integrations PRIMARY KEY (id), 
    CONSTRAINT uq_notion_integrations_user_id_name UNIQUE (user_id, name), 
    CONSTRAINT fk_notion_integrations_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE notion_data_sources (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    integration_id UUID NOT NULL, 
    source_type VARCHAR(20) NOT NULL, 
    external_source_id VARCHAR(128) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    sync_interval_minutes INTEGER DEFAULT 60 NOT NULL, 
    is_enabled BOOLEAN DEFAULT true NOT NULL, 
    last_edited_watermark TIMESTAMP WITH TIME ZONE, 
    last_cursor TEXT, 
    next_sync_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notion_data_sources PRIMARY KEY (id), 
    CONSTRAINT ck_notion_data_sources_ck_notion_data_sources_source_type CHECK (source_type IN ('database','page_tree')), 
    CONSTRAINT ck_notion_data_sources_ck_notion_data_sources_sync_interval CHECK (sync_interval_minutes >= 5), 
    CONSTRAINT uq_notion_data_sources_integration_external UNIQUE (integration_id, external_source_id), 
    CONSTRAINT fk_notion_data_sources_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notion_data_sources_integration_id_notion_integrations FOREIGN KEY(integration_id) REFERENCES notion_integrations (id) ON DELETE RESTRICT
);

CREATE TABLE sync_runs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    data_source_id UUID NOT NULL, 
    trigger_type VARCHAR(20) NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    watermark_from TIMESTAMP WITH TIME ZONE, 
    watermark_to TIMESTAMP WITH TIME ZONE, 
    cursor_from TEXT, 
    cursor_to TEXT, 
    items_seen INTEGER DEFAULT 0 NOT NULL, 
    items_imported INTEGER DEFAULT 0 NOT NULL, 
    items_failed INTEGER DEFAULT 0 NOT NULL, 
    attempt INTEGER DEFAULT 1 NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    next_retry_at TIMESTAMP WITH TIME ZONE, 
    error_code TEXT, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_sync_runs PRIMARY KEY (id), 
    CONSTRAINT ck_sync_runs_ck_sync_runs_trigger_type CHECK (trigger_type IN ('manual','scheduled')), 
    CONSTRAINT ck_sync_runs_ck_sync_runs_status CHECK (status IN ('pending','running','succeeded','failed','partial','cancelled')), 
    CONSTRAINT uq_sync_runs_user_id_idempotency_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_sync_runs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_sync_runs_data_source_id_notion_data_sources FOREIGN KEY(data_source_id) REFERENCES notion_data_sources (id) ON DELETE RESTRICT
);

CREATE TABLE raw_notes (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    data_source_id UUID NOT NULL, 
    sync_run_id UUID NOT NULL, 
    external_page_id VARCHAR(128) NOT NULL, 
    external_version VARCHAR(128) NOT NULL, 
    last_edited_time TIMESTAMP WITH TIME ZONE NOT NULL, 
    title TEXT, 
    content_markdown TEXT, 
    content_hash CHAR(64) NOT NULL, 
    source_url TEXT, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_raw_notes PRIMARY KEY (id), 
    CONSTRAINT uq_raw_notes_source_page_version UNIQUE (data_source_id, external_page_id, external_version), 
    CONSTRAINT fk_raw_notes_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_raw_notes_data_source_id_notion_data_sources FOREIGN KEY(data_source_id) REFERENCES notion_data_sources (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_raw_notes_sync_run_id_sync_runs FOREIGN KEY(sync_run_id) REFERENCES sync_runs (id) ON DELETE RESTRICT
);

CREATE TABLE ai_provider_configs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    model_name VARCHAR(120) NOT NULL, 
    base_url TEXT, 
    credential_ref VARCHAR(160) NOT NULL, 
    temperature NUMERIC(3, 2) DEFAULT 0.2 NOT NULL, 
    timeout_seconds INTEGER DEFAULT 60 NOT NULL, 
    max_retries INTEGER DEFAULT 3 NOT NULL, 
    rate_limit_per_minute INTEGER, 
    is_enabled BOOLEAN DEFAULT true NOT NULL, 
    is_default BOOLEAN DEFAULT false NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_provider_configs PRIMARY KEY (id), 
    CONSTRAINT ck_ai_provider_configs_ck_ai_provider_configs_provider CHECK (provider IN ('openai','deepseek','openai_compatible')), 
    CONSTRAINT ck_ai_provider_configs_ck_ai_provider_configs_temperature CHECK (temperature BETWEEN 0 AND 2), 
    CONSTRAINT ck_ai_provider_configs_ck_ai_provider_configs_timeout CHECK (timeout_seconds > 0), 
    CONSTRAINT ck_ai_provider_configs_ck_ai_provider_configs_max_retries CHECK (max_retries >= 0), 
    CONSTRAINT uq_ai_provider_configs_user_id_name UNIQUE (user_id, name), 
    CONSTRAINT fk_ai_provider_configs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE ai_call_logs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    provider_config_id UUID NOT NULL, 
    operation VARCHAR(40) NOT NULL, 
    provider VARCHAR(32) NOT NULL, 
    model_name VARCHAR(120) NOT NULL, 
    prompt_version VARCHAR(40) NOT NULL, 
    request_id UUID NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    input_tokens INTEGER, 
    output_tokens INTEGER, 
    total_tokens INTEGER, 
    duration_ms INTEGER, 
    attempt_count INTEGER DEFAULT 1 NOT NULL, 
    error_code TEXT, 
    error_message TEXT, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_ai_call_logs PRIMARY KEY (id), 
    CONSTRAINT ck_ai_call_logs_ck_ai_call_logs_provider CHECK (provider IN ('openai','deepseek','openai_compatible')), 
    CONSTRAINT ck_ai_call_logs_ck_ai_call_logs_status CHECK (status IN ('pending','running','succeeded','failed','cancelled')), 
    CONSTRAINT fk_ai_call_logs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_ai_call_logs_provider_config_id_ai_provider_configs FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs (id) ON DELETE RESTRICT
);

CREATE TABLE knowledge_points (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    subject_id UUID NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    body TEXT NOT NULL, 
    summary TEXT NOT NULL, 
    difficulty SMALLINT NOT NULL, 
    keywords JSONB DEFAULT '[]'::jsonb NOT NULL, 
    tags JSONB DEFAULT '[]'::jsonb NOT NULL, 
    status VARCHAR(20) DEFAULT 'draft' NOT NULL, 
    merged_into_id UUID, 
    canonical_hash CHAR(64) NOT NULL, 
    manual_revision BOOLEAN DEFAULT false NOT NULL, 
    source_generated_at TIMESTAMP WITH TIME ZONE, 
    archived_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_knowledge_points PRIMARY KEY (id), 
    CONSTRAINT ck_knowledge_points_ck_knowledge_points_difficulty CHECK (difficulty BETWEEN 1 AND 5), 
    CONSTRAINT ck_knowledge_points_ck_knowledge_points_status CHECK (status IN ('draft','active','archived','merged')), 
    CONSTRAINT fk_knowledge_points_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_knowledge_points_subject_id_subjects FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_knowledge_points_merged_into_id_knowledge_points FOREIGN KEY(merged_into_id) REFERENCES knowledge_points (id) ON DELETE RESTRICT
);

CREATE TABLE knowledge_point_sources (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    knowledge_point_id UUID NOT NULL, 
    raw_note_id UUID NOT NULL, 
    source_excerpt TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_knowledge_point_sources PRIMARY KEY (id), 
    CONSTRAINT uq_knowledge_point_sources_kp_raw_note UNIQUE (knowledge_point_id, raw_note_id), 
    CONSTRAINT fk_knowledge_point_sources_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_knowledge_point_sources_knowledge_point_id_knowledge_points FOREIGN KEY(knowledge_point_id) REFERENCES knowledge_points (id) ON DELETE CASCADE, 
    CONSTRAINT fk_knowledge_point_sources_raw_note_id_raw_notes FOREIGN KEY(raw_note_id) REFERENCES raw_notes (id) ON DELETE RESTRICT
);

CREATE TABLE review_items (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    knowledge_point_id UUID NOT NULL, 
    question_type VARCHAR(24) NOT NULL, 
    question TEXT NOT NULL, 
    answer TEXT NOT NULL, 
    explanation TEXT DEFAULT '' NOT NULL, 
    summary TEXT DEFAULT '' NOT NULL, 
    options JSONB, 
    item_version INTEGER DEFAULT 1 NOT NULL, 
    is_current BOOLEAN DEFAULT true NOT NULL, 
    manual_revision BOOLEAN DEFAULT false NOT NULL, 
    provider_config_id UUID, 
    model_name VARCHAR(120), 
    prompt_version VARCHAR(40), 
    ai_call_log_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_review_items PRIMARY KEY (id), 
    CONSTRAINT ck_review_items_ck_review_items_question_type CHECK (question_type IN ('qa','cloze','multiple_choice','short_explanation')), 
    CONSTRAINT ck_review_items_ck_review_items_item_version CHECK (item_version >= 1), 
    CONSTRAINT uq_review_items_kp_type_version UNIQUE (knowledge_point_id, question_type, item_version), 
    CONSTRAINT fk_review_items_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_review_items_knowledge_point_id_knowledge_points FOREIGN KEY(knowledge_point_id) REFERENCES knowledge_points (id) ON DELETE CASCADE, 
    CONSTRAINT fk_review_items_provider_config_id_ai_provider_configs FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_review_items_ai_call_log_id_ai_call_logs FOREIGN KEY(ai_call_log_id) REFERENCES ai_call_logs (id) ON DELETE RESTRICT
);

CREATE TABLE schedule_states (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    knowledge_point_id UUID NOT NULL, 
    strategy VARCHAR(20) DEFAULT 'ebbinghaus' NOT NULL, 
    state_version INTEGER DEFAULT 1 NOT NULL, 
    due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_reviewed_at TIMESTAMP WITH TIME ZONE, 
    review_count INTEGER DEFAULT 0 NOT NULL, 
    lapse_count INTEGER DEFAULT 0 NOT NULL, 
    interval_index INTEGER DEFAULT 0 NOT NULL, 
    interval_days NUMERIC(10, 3), 
    stability NUMERIC(12, 6), 
    difficulty NUMERIC(8, 6), 
    retrievability NUMERIC(8, 6), 
    target_retention NUMERIC(5, 4), 
    algorithm_version VARCHAR(40) NOT NULL, 
    parameters JSONB DEFAULT '{}'::jsonb NOT NULL, 
    last_calculation JSONB DEFAULT '{}'::jsonb NOT NULL, 
    strategy_changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_schedule_states PRIMARY KEY (id), 
    CONSTRAINT ck_schedule_states_ck_schedule_states_strategy CHECK (strategy IN ('ebbinghaus','fsrs')), 
    CONSTRAINT uq_schedule_states_knowledge_point_id UNIQUE (knowledge_point_id), 
    CONSTRAINT fk_schedule_states_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_schedule_states_knowledge_point_id_knowledge_points FOREIGN KEY(knowledge_point_id) REFERENCES knowledge_points (id) ON DELETE RESTRICT
);

CREATE TABLE daily_review_batches (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    local_date DATE NOT NULL, 
    timezone VARCHAR(64) NOT NULL, 
    subject_id UUID, 
    daily_limit INTEGER NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_daily_review_batches PRIMARY KEY (id), 
    CONSTRAINT ck_daily_review_batches_ck_daily_review_batches_status CHECK (status IN ('pending','ready','completed','cancelled')), 
    CONSTRAINT uq_daily_review_batches_user_id_idempotency_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_daily_review_batches_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE daily_review_tasks (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    batch_id UUID NOT NULL, 
    knowledge_point_id UUID NOT NULL, 
    review_item_id UUID, 
    scheduled_due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    priority INTEGER DEFAULT 0 NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    position INTEGER NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_daily_review_tasks PRIMARY KEY (id), 
    CONSTRAINT ck_daily_review_tasks_ck_daily_review_tasks_status CHECK (status IN ('pending','in_progress','completed','skipped','cancelled')), 
    CONSTRAINT uq_daily_review_tasks_batch_kp UNIQUE (batch_id, knowledge_point_id), 
    CONSTRAINT fk_daily_review_tasks_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_daily_review_tasks_batch_id_daily_review_batches FOREIGN KEY(batch_id) REFERENCES daily_review_batches (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_daily_review_tasks_knowledge_point_id_knowledge_points FOREIGN KEY(knowledge_point_id) REFERENCES knowledge_points (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_daily_review_tasks_review_item_id_review_items FOREIGN KEY(review_item_id) REFERENCES review_items (id) ON DELETE RESTRICT
);

CREATE TABLE review_history (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    task_id UUID NOT NULL, 
    knowledge_point_id UUID NOT NULL, 
    review_item_id UUID, 
    strategy VARCHAR(20) NOT NULL, 
    rating VARCHAR(16) NOT NULL, 
    duration_seconds INTEGER NOT NULL, 
    answer_self_assessment TEXT, 
    notes TEXT, 
    reviewed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    previous_schedule JSONB DEFAULT '{}'::jsonb NOT NULL, 
    result_schedule JSONB DEFAULT '{}'::jsonb NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_review_history PRIMARY KEY (id), 
    CONSTRAINT ck_review_history_ck_review_history_strategy CHECK (strategy IN ('ebbinghaus','fsrs')), 
    CONSTRAINT ck_review_history_ck_review_history_rating CHECK (rating IN ('again','hard','good','easy')), 
    CONSTRAINT ck_review_history_ck_review_history_duration_seconds CHECK (duration_seconds >= 0), 
    CONSTRAINT uq_review_history_task_id UNIQUE (task_id), 
    CONSTRAINT uq_review_history_user_id_idempotency_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_review_history_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_review_history_task_id_daily_review_tasks FOREIGN KEY(task_id) REFERENCES daily_review_tasks (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_review_history_knowledge_point_id_knowledge_points FOREIGN KEY(knowledge_point_id) REFERENCES knowledge_points (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_review_history_review_item_id_review_items FOREIGN KEY(review_item_id) REFERENCES review_items (id) ON DELETE RESTRICT
);

CREATE TABLE notification_channel_configs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    channel_type VARCHAR(40) NOT NULL, 
    credential_ref VARCHAR(160) NOT NULL, 
    settings JSONB DEFAULT '{}'::jsonb NOT NULL, 
    is_enabled BOOLEAN DEFAULT true NOT NULL, 
    is_default BOOLEAN DEFAULT false NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notification_channel_configs PRIMARY KEY (id), 
    CONSTRAINT ck_notification_channel_configs_ck_channel_configs_channel_type CHECK (channel_type IN ('wecom_app','wechat_official_account','third_party_push','wecom_webhook','dingtalk_webhook','dingtalk_app','smtp')), 
    CONSTRAINT uq_channel_configs_user_id_name UNIQUE (user_id, name), 
    CONSTRAINT fk_notification_channel_configs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE notification_templates (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    subject_id UUID, 
    channel_type VARCHAR(40) NOT NULL, 
    template_key VARCHAR(80) NOT NULL, 
    title_template TEXT NOT NULL, 
    body_template TEXT NOT NULL, 
    schema_variables JSONB DEFAULT '[]'::jsonb NOT NULL, 
    max_length INTEGER, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notification_templates PRIMARY KEY (id), 
    CONSTRAINT ck_notification_templates_ck_templates_channel_type CHECK (channel_type IN ('wecom_app','wechat_official_account','third_party_push','wecom_webhook','dingtalk_webhook','dingtalk_app','smtp')), 
    CONSTRAINT uq_templates_user_subject_type_key_version UNIQUE (user_id, subject_id, channel_type, template_key, version), 
    CONSTRAINT fk_notification_templates_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notification_templates_subject_id_subjects FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT
);

CREATE TABLE notification_jobs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    task_id UUID NOT NULL, 
    channel_config_id UUID NOT NULL, 
    template_id UUID NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    idempotency_key VARCHAR(128) NOT NULL, 
    rendered_title TEXT, 
    rendered_body TEXT, 
    attempt_count INTEGER DEFAULT 0 NOT NULL, 
    max_attempts INTEGER NOT NULL, 
    next_attempt_at TIMESTAMP WITH TIME ZONE, 
    last_error_code TEXT, 
    last_error_message TEXT, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notification_jobs PRIMARY KEY (id), 
    CONSTRAINT ck_notification_jobs_ck_notification_jobs_status CHECK (status IN ('pending','processing','sent','failed','cancelled')), 
    CONSTRAINT uq_notification_jobs_user_id_idempotency_key UNIQUE (user_id, idempotency_key), 
    CONSTRAINT fk_notification_jobs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notification_jobs_task_id_daily_review_tasks FOREIGN KEY(task_id) REFERENCES daily_review_tasks (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notification_jobs_channel_config_id_notification_cha_1bdc FOREIGN KEY(channel_config_id) REFERENCES notification_channel_configs (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notification_jobs_template_id_notification_templates FOREIGN KEY(template_id) REFERENCES notification_templates (id) ON DELETE RESTRICT
);

CREATE TABLE notification_deliveries (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    job_id UUID NOT NULL, 
    attempt_no INTEGER NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    provider_message_id VARCHAR(256), 
    request_metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    response_metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    error_code TEXT, 
    error_message TEXT, 
    duration_ms INTEGER, 
    attempted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notification_deliveries PRIMARY KEY (id), 
    CONSTRAINT ck_notification_deliveries_ck_notification_deliveries_status CHECK (status IN ('sending','sent','failed')), 
    CONSTRAINT uq_notification_deliveries_job_attempt UNIQUE (job_id, attempt_no), 
    CONSTRAINT fk_notification_deliveries_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_notification_deliveries_job_id_notification_jobs FOREIGN KEY(job_id) REFERENCES notification_jobs (id) ON DELETE RESTRICT
);

CREATE INDEX ix_users_is_active ON users (is_active);

CREATE INDEX ix_subjects_user_id_parent_id ON subjects (user_id, parent_id);

CREATE INDEX ix_subjects_tags_gin ON subjects USING gin (tags);

CREATE UNIQUE INDEX uq_subject_strategies_active_subject ON subject_strategies (subject_id) WHERE is_active;

CREATE INDEX ix_subject_strategies_user_id_subject_id ON subject_strategies (user_id, subject_id);

CREATE INDEX ix_notion_data_sources_enabled_next_sync ON notion_data_sources (is_enabled, next_sync_at);

CREATE INDEX ix_sync_runs_source_created ON sync_runs (data_source_id, created_at DESC);

CREATE INDEX ix_sync_runs_status_next_retry ON sync_runs (status, next_retry_at);

CREATE INDEX ix_raw_notes_user_last_edited ON raw_notes (user_id, last_edited_time);

CREATE INDEX ix_raw_notes_content_hash ON raw_notes (content_hash);

CREATE UNIQUE INDEX uq_knowledge_points_user_canonical_hash ON knowledge_points (user_id, canonical_hash) WHERE status <> 'merged';

CREATE INDEX ix_knowledge_points_user_subject_status ON knowledge_points (user_id, subject_id, status);

CREATE INDEX ix_knowledge_points_keywords_gin ON knowledge_points USING gin (keywords);

CREATE INDEX ix_knowledge_points_tags_gin ON knowledge_points USING gin (tags);

CREATE INDEX ix_knowledge_point_sources_raw_note_id ON knowledge_point_sources (raw_note_id);

CREATE UNIQUE INDEX uq_review_items_current ON review_items (knowledge_point_id) WHERE is_current;

CREATE INDEX ix_review_items_user_id ON review_items (user_id);

CREATE INDEX ix_schedule_states_user_due ON schedule_states (user_id, due_at);

CREATE INDEX ix_schedule_states_strategy_due ON schedule_states (strategy, due_at);

CREATE UNIQUE INDEX uq_daily_review_batches_user_date_subject ON daily_review_batches (user_id, local_date, subject_id) NULLS NOT DISTINCT;

CREATE INDEX ix_daily_review_tasks_user_status_due ON daily_review_tasks (user_id, status, scheduled_due_at);

CREATE INDEX ix_daily_review_tasks_batch_position ON daily_review_tasks (batch_id, position);

CREATE INDEX ix_review_history_user_reviewed ON review_history (user_id, reviewed_at DESC);

CREATE INDEX ix_review_history_kp_reviewed ON review_history (knowledge_point_id, reviewed_at DESC);

CREATE UNIQUE INDEX uq_channel_configs_default ON notification_channel_configs (user_id) WHERE is_default;

CREATE INDEX ix_channel_configs_user_type_enabled ON notification_channel_configs (user_id, channel_type, is_enabled);

CREATE INDEX ix_templates_active_lookup ON notification_templates (user_id, channel_type, template_key) WHERE is_active;

CREATE INDEX ix_notification_jobs_status_next_attempt ON notification_jobs (status, next_attempt_at);

CREATE INDEX ix_notification_jobs_task_id ON notification_jobs (task_id);

CREATE INDEX ix_notification_deliveries_user_attempted ON notification_deliveries (user_id, attempted_at DESC);

CREATE UNIQUE INDEX uq_ai_provider_configs_default ON ai_provider_configs (user_id) WHERE is_default;

CREATE INDEX ix_ai_call_logs_user_created ON ai_call_logs (user_id, created_at DESC);

CREATE INDEX ix_ai_call_logs_status_created ON ai_call_logs (status, created_at);

CREATE INDEX ix_ai_call_logs_request_id ON ai_call_logs (request_id);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema') RETURNING alembic_version.version_num;

-- Running upgrade 0001_initial_schema -> 0002_accounts_learning

ALTER TABLE users ADD COLUMN role varchar(16) NOT NULL DEFAULT 'user';

ALTER TABLE users ADD COLUMN version integer NOT NULL DEFAULT 1;

ALTER TABLE daily_review_batches ADD COLUMN version integer NOT NULL DEFAULT 1;

ALTER TABLE knowledge_points ADD COLUMN chapter_id uuid;

ALTER TABLE users ADD CONSTRAINT ck_users_user_role CHECK (role IN ('user','admin'));

ALTER TABLE subjects ADD CONSTRAINT uq_owner_subjects_3557ea50 UNIQUE (user_id, id);

ALTER TABLE notion_integrations ADD CONSTRAINT uq_owner_notion_integrations_e489aa8a UNIQUE (user_id, id);

ALTER TABLE notion_data_sources ADD CONSTRAINT uq_owner_notion_data_sources_b4efdfaf UNIQUE (user_id, id);

ALTER TABLE sync_runs ADD CONSTRAINT uq_owner_sync_runs_0d1553da UNIQUE (user_id, id);

ALTER TABLE raw_notes ADD CONSTRAINT uq_owner_raw_notes_c0c742a3 UNIQUE (user_id, id);

ALTER TABLE knowledge_points ADD CONSTRAINT uq_owner_knowledge_points_b309a4bf UNIQUE (user_id, id);

ALTER TABLE review_items ADD CONSTRAINT uq_owner_review_items_b0c77377 UNIQUE (user_id, id);

ALTER TABLE daily_review_batches ADD CONSTRAINT uq_owner_daily_review_batches_80b30846 UNIQUE (user_id, id);

ALTER TABLE daily_review_tasks ADD CONSTRAINT uq_owner_daily_review_tasks_e29f59c0 UNIQUE (user_id, id);

ALTER TABLE notification_channel_configs ADD CONSTRAINT uq_owner_notification_channel_configs_d5cb4ab7 UNIQUE (user_id, id);

ALTER TABLE notification_templates ADD CONSTRAINT uq_owner_notification_templates_383789cf UNIQUE (user_id, id);

ALTER TABLE notification_jobs ADD CONSTRAINT uq_owner_notification_jobs_de439dac UNIQUE (user_id, id);

ALTER TABLE ai_provider_configs ADD CONSTRAINT uq_owner_ai_provider_configs_3f781400 UNIQUE (user_id, id);

ALTER TABLE ai_call_logs ADD CONSTRAINT uq_owner_ai_call_logs_a9933630 UNIQUE (user_id, id);

CREATE TABLE login_throttles (
    key VARCHAR(80) NOT NULL, 
    failures INTEGER DEFAULT 0 NOT NULL, 
    window_started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_login_throttles PRIMARY KEY (key), 
    CONSTRAINT ck_login_throttles_throttle_failures CHECK (failures >= 0)
);

CREATE TABLE audit_events (
    actor_id UUID, 
    target_user_id UUID, 
    actor_label VARCHAR(254) NOT NULL, 
    action VARCHAR(64) NOT NULL, 
    severity VARCHAR(16) DEFAULT 'info' NOT NULL, 
    resource VARCHAR(300) NOT NULL, 
    outcome VARCHAR(32) NOT NULL, 
    ip_address VARCHAR(64) NOT NULL, 
    request_id UUID, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_audit_events PRIMARY KEY (id), 
    CONSTRAINT ck_audit_events_audit_severity CHECK (severity IN ('info','warning','high')), 
    CONSTRAINT fk_audit_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_audit_events_target_user_id_users FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_audit_actor_created ON audit_events (actor_id, created_at);

CREATE INDEX ix_audit_created ON audit_events (created_at, id);

CREATE TABLE idempotency_records (
    operation VARCHAR(160) NOT NULL, 
    key VARCHAR(128) NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    resource_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_idempotency_records PRIMARY KEY (id), 
    CONSTRAINT uq_idempotency_scope UNIQUE (user_id, operation, key), 
    CONSTRAINT fk_idempotency_records_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE user_sessions (
    token_digest VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    logged_out_at TIMESTAMP WITH TIME ZONE, 
    ip_address VARCHAR(64) NOT NULL, 
    user_agent VARCHAR(500) NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    CONSTRAINT pk_user_sessions PRIMARY KEY (id), 
    CONSTRAINT ck_user_sessions_session_expiry CHECK (expires_at > created_at), 
    CONSTRAINT uq_user_sessions_token_digest UNIQUE (token_digest), 
    CONSTRAINT fk_user_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE INDEX ix_sessions_online ON user_sessions (last_seen_at, expires_at) WHERE logged_out_at IS NULL;

CREATE INDEX ix_sessions_user_created ON user_sessions (user_id, created_at);

CREATE TABLE chapters (
    subject_id UUID NOT NULL, 
    title VARCHAR(300) NOT NULL, 
    content TEXT DEFAULT '' NOT NULL, 
    status VARCHAR(20) DEFAULT 'not_started' NOT NULL, 
    source_url TEXT, 
    external_page_id VARCHAR(128), 
    completed_at TIMESTAMP WITH TIME ZONE, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    version INTEGER DEFAULT 1 NOT NULL, 
    CONSTRAINT pk_chapters PRIMARY KEY (id), 
    CONSTRAINT ck_chapters_chapter_status CHECK (status IN ('not_started','in_progress','completed')), 
    CONSTRAINT uq_chapter_external_page UNIQUE (user_id, external_page_id), 
    CONSTRAINT fk_chapters_subject_id_subjects FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_chapters_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_owner_chapters_b0c17653 UNIQUE (user_id, id), 
    CONSTRAINT fk_owner_chapters_ebd5e656 FOREIGN KEY(user_id, subject_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_chapters_user_subject_status ON chapters (user_id, subject_id, status);

CREATE TABLE study_sessions (
    chapter_id UUID NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    ended_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    duration_seconds INTEGER NOT NULL, 
    notes TEXT DEFAULT '' NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_study_sessions PRIMARY KEY (id), 
    CONSTRAINT ck_study_sessions_study_session_time CHECK (ended_at >= started_at AND duration_seconds >= 0), 
    CONSTRAINT fk_study_sessions_chapter_id_chapters FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_study_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_owner_study_sessions_bfafeefa FOREIGN KEY(user_id, chapter_id) REFERENCES chapters (user_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_study_user_chapter ON study_sessions (user_id, chapter_id);

CREATE TABLE chapter_jobs (
    chapter_id UUID NOT NULL, 
    content_hash VARCHAR(64) NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    attempt INTEGER DEFAULT 0 NOT NULL, 
    error_code VARCHAR(80), 
    next_attempt_at TIMESTAMP WITH TIME ZONE, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    result JSONB DEFAULT '{}'::jsonb NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_chapter_jobs PRIMARY KEY (id), 
    CONSTRAINT uq_chapter_job_revision UNIQUE (chapter_id, content_hash), 
    CONSTRAINT ck_chapter_jobs_chapter_job_status CHECK (status IN ('pending','running','blocked','succeeded','failed','cancelled')), 
    CONSTRAINT fk_chapter_jobs_chapter_id_chapters FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_chapter_jobs_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_owner_chapter_jobs_713368db FOREIGN KEY(user_id, chapter_id) REFERENCES chapters (user_id, id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_chapter_jobs_retry ON chapter_jobs (status, next_attempt_at);

ALTER TABLE subjects ADD CONSTRAINT fk_owner_subjects_2eef41ad FOREIGN KEY(user_id, parent_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE subject_strategies ADD CONSTRAINT fk_owner_subject_strategies_c6a42ca5 FOREIGN KEY(user_id, subject_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notion_data_sources ADD CONSTRAINT fk_owner_notion_data_sources_e369d74a FOREIGN KEY(user_id, integration_id) REFERENCES notion_integrations (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE sync_runs ADD CONSTRAINT fk_owner_sync_runs_e7494b45 FOREIGN KEY(user_id, data_source_id) REFERENCES notion_data_sources (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE raw_notes ADD CONSTRAINT fk_owner_raw_notes_78a92210 FOREIGN KEY(user_id, sync_run_id) REFERENCES sync_runs (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE raw_notes ADD CONSTRAINT fk_owner_raw_notes_8c382e8b FOREIGN KEY(user_id, data_source_id) REFERENCES notion_data_sources (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowledge_points ADD CONSTRAINT fk_knowledge_points_chapter_id_chapters FOREIGN KEY(chapter_id) REFERENCES chapters (id) ON DELETE RESTRICT;

ALTER TABLE knowledge_points ADD CONSTRAINT fk_owner_knowledge_points_27668ce9 FOREIGN KEY(user_id, chapter_id) REFERENCES chapters (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowledge_points ADD CONSTRAINT fk_owner_knowledge_points_3bf26714 FOREIGN KEY(user_id, merged_into_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowledge_points ADD CONSTRAINT fk_owner_knowledge_points_d99e03b4 FOREIGN KEY(user_id, subject_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowledge_point_sources ADD CONSTRAINT fk_owner_knowledge_point_sources_17b56986 FOREIGN KEY(user_id, knowledge_point_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowledge_point_sources ADD CONSTRAINT fk_owner_knowledge_point_sources_ae3ce7e2 FOREIGN KEY(user_id, raw_note_id) REFERENCES raw_notes (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_items ADD CONSTRAINT fk_owner_review_items_33a20e78 FOREIGN KEY(user_id, provider_config_id) REFERENCES ai_provider_configs (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_items ADD CONSTRAINT fk_owner_review_items_bf5dd72a FOREIGN KEY(user_id, knowledge_point_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_items ADD CONSTRAINT fk_owner_review_items_f9e5a9b6 FOREIGN KEY(user_id, ai_call_log_id) REFERENCES ai_call_logs (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE schedule_states ADD CONSTRAINT fk_owner_schedule_states_84b06532 FOREIGN KEY(user_id, knowledge_point_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE daily_review_tasks ADD CONSTRAINT fk_owner_daily_review_tasks_737ffd2c FOREIGN KEY(user_id, batch_id) REFERENCES daily_review_batches (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE daily_review_tasks ADD CONSTRAINT fk_owner_daily_review_tasks_c00e6838 FOREIGN KEY(user_id, review_item_id) REFERENCES review_items (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE daily_review_tasks ADD CONSTRAINT fk_owner_daily_review_tasks_dc7412a5 FOREIGN KEY(user_id, knowledge_point_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_history ADD CONSTRAINT fk_owner_review_history_0ca71523 FOREIGN KEY(user_id, task_id) REFERENCES daily_review_tasks (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_history ADD CONSTRAINT fk_owner_review_history_ae1bcae0 FOREIGN KEY(user_id, knowledge_point_id) REFERENCES knowledge_points (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE review_history ADD CONSTRAINT fk_owner_review_history_e0515e4e FOREIGN KEY(user_id, review_item_id) REFERENCES review_items (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notification_templates ADD CONSTRAINT fk_owner_notification_templates_e1670e5e FOREIGN KEY(user_id, subject_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notification_jobs ADD CONSTRAINT fk_owner_notification_jobs_18427830 FOREIGN KEY(user_id, task_id) REFERENCES daily_review_tasks (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notification_jobs ADD CONSTRAINT fk_owner_notification_jobs_8aab2e3d FOREIGN KEY(user_id, channel_config_id) REFERENCES notification_channel_configs (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notification_jobs ADD CONSTRAINT fk_owner_notification_jobs_a1cfaa16 FOREIGN KEY(user_id, template_id) REFERENCES notification_templates (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notification_deliveries ADD CONSTRAINT fk_owner_notification_deliveries_7306a6f4 FOREIGN KEY(user_id, job_id) REFERENCES notification_jobs (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ai_call_logs ADD CONSTRAINT fk_owner_ai_call_logs_1480072f FOREIGN KEY(user_id, provider_config_id) REFERENCES ai_provider_configs (user_id, id) DEFERRABLE INITIALLY DEFERRED;;

UPDATE alembic_version SET version_num='0002_accounts_learning' WHERE alembic_version.version_num = '0001_initial_schema';

-- Running upgrade 0002_accounts_learning -> 0003_task_skip_reason

ALTER TABLE daily_review_tasks ADD COLUMN skip_reason TEXT;

UPDATE alembic_version SET version_num='0003_task_skip_reason' WHERE alembic_version.version_num = '0002_accounts_learning';

-- Running upgrade 0003_task_skip_reason -> 0004_notion_sources

ALTER TABLE notion_data_sources DROP CONSTRAINT ck_notion_data_sources_ck_notion_data_sources_source_type;

ALTER TABLE notion_data_sources ADD CONSTRAINT ck_notion_data_sources_ck_notion_data_sources_source_type CHECK (source_type IN ('database','data_source','page_tree'));

ALTER TABLE notion_data_sources ADD COLUMN subject_id UUID;

ALTER TABLE notion_data_sources ADD COLUMN status_property VARCHAR(120) DEFAULT '状态' NOT NULL;

ALTER TABLE notion_data_sources ADD COLUMN status_mapping JSONB DEFAULT '{"未开始":"not_started","进行中":"in_progress","已完成":"completed"}'::jsonb NOT NULL;

ALTER TABLE notion_data_sources ADD COLUMN pending_watermark TIMESTAMP WITH TIME ZONE;

ALTER TABLE notion_data_sources ADD CONSTRAINT fk_owner_notion_data_sources_1acee312 FOREIGN KEY(user_id, subject_id) REFERENCES subjects (user_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE notion_data_sources ADD CONSTRAINT fk_notion_data_sources_subject_id_subjects FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE RESTRICT;

UPDATE alembic_version SET version_num='0004_notion_sources' WHERE alembic_version.version_num = '0003_task_skip_reason';

-- Running upgrade 0004_notion_sources -> 0005_guided_setup

CREATE TABLE user_secrets (
    name VARCHAR(160) NOT NULL,
    ciphertext TEXT NOT NULL,
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_user_secrets PRIMARY KEY (id),
    CONSTRAINT fk_user_secrets_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_user_secret_name UNIQUE (user_id, name)
);

CREATE TABLE workspace_profiles (
    onboarding_step INTEGER DEFAULT 0 NOT NULL,
    onboarding_completed_at TIMESTAMP WITH TIME ZONE,
    recipient_email VARCHAR(254),
    reminder_time VARCHAR(5) DEFAULT '09:00' NOT NULL,
    email_enabled BOOLEAN DEFAULT false NOT NULL,
    ai_billing_approved BOOLEAN DEFAULT false NOT NULL,
    email_settings JSONB DEFAULT '{}'::jsonb NOT NULL,
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    CONSTRAINT pk_workspace_profiles PRIMARY KEY (id),
    CONSTRAINT ck_workspace_profiles_onboarding_step_range CHECK (onboarding_step BETWEEN 0 AND 4),
    CONSTRAINT fk_workspace_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT uq_workspace_profile_user UNIQUE (user_id)
);

ALTER TABLE notification_jobs ADD COLUMN purpose VARCHAR(20) DEFAULT 'review' NOT NULL;

ALTER TABLE notification_jobs ADD COLUMN locked_until TIMESTAMP WITH TIME ZONE;

ALTER TABLE notification_jobs ALTER COLUMN task_id DROP NOT NULL;

UPDATE alembic_version SET version_num='0005_guided_setup' WHERE alembic_version.version_num = '0004_notion_sources';

COMMIT;

BEGIN;

ALTER TABLE chapters ADD COLUMN notion_archived_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE notion_data_sources ADD COLUMN lifecycle_cursor VARCHAR(128);
ALTER TABLE workspace_profiles ADD COLUMN review_preferences JSONB DEFAULT '{}'::jsonb NOT NULL;

UPDATE alembic_version SET version_num='0006_notion_lifecycle' WHERE alembic_version.version_num = '0005_guided_setup';

COMMIT;


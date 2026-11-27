"""Accounts, sessions, chapters and tenant ownership constraints."""
from alembic import op
revision = '0002_accounts_learning'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None

DDL = r"""
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

ALTER TABLE ai_call_logs ADD CONSTRAINT fk_owner_ai_call_logs_1480072f FOREIGN KEY(user_id, provider_config_id) REFERENCES ai_provider_configs (user_id, id) DEFERRABLE INITIALLY DEFERRED;
"""

def upgrade():
    op.execute(DDL)

def downgrade():
    op.drop_constraint('fk_owner_ai_call_logs_1480072f', 'ai_call_logs')
    op.drop_constraint('fk_owner_daily_review_tasks_737ffd2c', 'daily_review_tasks')
    op.drop_constraint('fk_owner_daily_review_tasks_c00e6838', 'daily_review_tasks')
    op.drop_constraint('fk_owner_daily_review_tasks_dc7412a5', 'daily_review_tasks')
    op.drop_constraint('fk_owner_knowledge_point_sources_17b56986', 'knowledge_point_sources')
    op.drop_constraint('fk_owner_knowledge_point_sources_ae3ce7e2', 'knowledge_point_sources')
    op.drop_constraint('fk_knowledge_points_chapter_id_chapters', 'knowledge_points')
    op.drop_constraint('fk_owner_knowledge_points_27668ce9', 'knowledge_points')
    op.drop_constraint('fk_owner_knowledge_points_3bf26714', 'knowledge_points')
    op.drop_constraint('fk_owner_knowledge_points_d99e03b4', 'knowledge_points')
    op.drop_constraint('fk_owner_notification_deliveries_7306a6f4', 'notification_deliveries')
    op.drop_constraint('fk_owner_notification_jobs_18427830', 'notification_jobs')
    op.drop_constraint('fk_owner_notification_jobs_8aab2e3d', 'notification_jobs')
    op.drop_constraint('fk_owner_notification_jobs_a1cfaa16', 'notification_jobs')
    op.drop_constraint('fk_owner_notification_templates_e1670e5e', 'notification_templates')
    op.drop_constraint('fk_owner_notion_data_sources_e369d74a', 'notion_data_sources')
    op.drop_constraint('fk_owner_raw_notes_78a92210', 'raw_notes')
    op.drop_constraint('fk_owner_raw_notes_8c382e8b', 'raw_notes')
    op.drop_constraint('fk_owner_review_history_0ca71523', 'review_history')
    op.drop_constraint('fk_owner_review_history_ae1bcae0', 'review_history')
    op.drop_constraint('fk_owner_review_history_e0515e4e', 'review_history')
    op.drop_constraint('fk_owner_review_items_33a20e78', 'review_items')
    op.drop_constraint('fk_owner_review_items_bf5dd72a', 'review_items')
    op.drop_constraint('fk_owner_review_items_f9e5a9b6', 'review_items')
    op.drop_constraint('fk_owner_schedule_states_84b06532', 'schedule_states')
    op.drop_constraint('fk_owner_subject_strategies_c6a42ca5', 'subject_strategies')
    op.drop_constraint('fk_owner_subjects_2eef41ad', 'subjects')
    op.drop_constraint('fk_owner_sync_runs_e7494b45', 'sync_runs')
    op.drop_column("knowledge_points", "chapter_id")
    op.drop_table('chapter_jobs')
    op.drop_table('study_sessions')
    op.drop_table('chapters')
    op.drop_table('user_sessions')
    op.drop_table('idempotency_records')
    op.drop_table('audit_events')
    op.drop_table('login_throttles')
    op.drop_constraint('uq_owner_ai_call_logs_a9933630', 'ai_call_logs')
    op.drop_constraint('uq_owner_ai_provider_configs_3f781400', 'ai_provider_configs')
    op.drop_constraint('uq_owner_daily_review_batches_80b30846', 'daily_review_batches')
    op.drop_constraint('uq_owner_daily_review_tasks_e29f59c0', 'daily_review_tasks')
    op.drop_constraint('uq_owner_knowledge_points_b309a4bf', 'knowledge_points')
    op.drop_constraint('uq_owner_notification_channel_configs_d5cb4ab7', 'notification_channel_configs')
    op.drop_constraint('uq_owner_notification_jobs_de439dac', 'notification_jobs')
    op.drop_constraint('uq_owner_notification_templates_383789cf', 'notification_templates')
    op.drop_constraint('uq_owner_notion_data_sources_b4efdfaf', 'notion_data_sources')
    op.drop_constraint('uq_owner_notion_integrations_e489aa8a', 'notion_integrations')
    op.drop_constraint('uq_owner_raw_notes_c0c742a3', 'raw_notes')
    op.drop_constraint('uq_owner_review_items_b0c77377', 'review_items')
    op.drop_constraint('uq_owner_subjects_3557ea50', 'subjects')
    op.drop_constraint('uq_owner_sync_runs_0d1553da', 'sync_runs')
    op.drop_constraint("ck_users_user_role", "users")
    op.drop_column("users", "role")
    op.drop_column("users", "version")
    op.drop_column("daily_review_batches", "version")

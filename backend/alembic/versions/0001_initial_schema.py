"""初始数据库迁移：按 DATABASE_SCHEMA.md 建立全部 20 张表（真实 SQL）。

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-11-13

PostgreSQL 为唯一目标库；``gen_random_uuid()`` / ``citext`` / ``jsonb`` 均为
PostgreSQL 特性。全部 ``op.create_table`` / ``op.create_index`` 为真实 DDL，
无占位。迁移脚本尚未在数据库中执行（凭据未确认、依赖未安装），如实标注。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


# ---- 通用列构造器（每次返回全新 Column 对象） ----
def _id():
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _user():
    return sa.Column(
        "user_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))


def _version():
    return sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))


def _jsonb_obj(name, nullable=False):
    return sa.Column(name, pg.JSONB(), nullable=nullable, server_default=sa.text("'{}'::jsonb"))


def _jsonb_arr(name):
    return sa.Column(name, pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ---- 身份与学科 ----
    op.create_table(
        "users",
        _id(),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "subjects",
        _id(), _user(),
        sa.Column("parent_id", pg.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language_code", sa.String(16), nullable=False, server_default=sa.text("'zh-CN'")),
        _jsonb_arr("tags"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _version(), *_timestamps(),
        sa.UniqueConstraint("user_id", "slug", name="uq_subjects_user_id_slug"),
    )
    op.create_table(
        "subject_strategies",
        _id(), _user(),
        sa.Column("subject_id", pg.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_prompt", sa.Text(), nullable=False),
        _jsonb_arr("question_type_preferences"),
        _jsonb_obj("glossary"),
        _jsonb_obj("scheduler_overrides"),
        _jsonb_obj("notification_template_overrides"),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _version(), *_timestamps(),
    )

    # ---- Notion 同步与原文 ----
    op.create_table(
        "notion_integrations",
        _id(), _user(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("credential_ref", sa.String(160), nullable=False),
        sa.Column("api_version", sa.String(20), nullable=False, server_default=sa.text("'2022-06-28'")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        _version(), *_timestamps(),
        sa.UniqueConstraint("user_id", "name", name="uq_notion_integrations_user_id_name"),
    )
    op.create_table(
        "notion_data_sources",
        _id(), _user(),
        sa.Column("integration_id", pg.UUID(as_uuid=True), sa.ForeignKey("notion_integrations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("external_source_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sync_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_edited_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        _version(), *_timestamps(),
        sa.CheckConstraint("source_type IN ('database','page_tree')", name="ck_notion_data_sources_source_type"),
        sa.CheckConstraint("sync_interval_minutes >= 5", name="ck_notion_data_sources_sync_interval"),
        sa.UniqueConstraint("integration_id", "external_source_id", name="uq_notion_data_sources_integration_external"),
    )
    op.create_table(
        "sync_runs",
        _id(), _user(),
        sa.Column("data_source_id", pg.UUID(as_uuid=True), sa.ForeignKey("notion_data_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("watermark_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("watermark_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_from", sa.Text(), nullable=True),
        sa.Column("cursor_to", sa.Text(), nullable=True),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_imported", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        _created(),
        sa.CheckConstraint("trigger_type IN ('manual','scheduled')", name="ck_sync_runs_trigger_type"),
        sa.CheckConstraint("status IN ('pending','running','succeeded','failed','partial','cancelled')", name="ck_sync_runs_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_sync_runs_user_id_idempotency_key"),
    )
    op.create_table(
        "raw_notes",
        _id(), _user(),
        sa.Column("data_source_id", pg.UUID(as_uuid=True), sa.ForeignKey("notion_data_sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sync_run_id", pg.UUID(as_uuid=True), sa.ForeignKey("sync_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_page_id", sa.String(128), nullable=False),
        sa.Column("external_version", sa.String(128), nullable=False),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        _jsonb_obj("metadata"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        _created(),
        sa.UniqueConstraint("data_source_id", "external_page_id", "external_version", name="uq_raw_notes_source_page_version"),
    )

    # ---- AI 配置与审计 ----
    op.create_table(
        "ai_provider_configs",
        _id(), _user(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("credential_ref", sa.String(160), nullable=False),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0.2")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _version(), *_timestamps(),
        sa.CheckConstraint("provider IN ('openai','deepseek','openai_compatible')", name="ck_ai_provider_configs_provider"),
        sa.CheckConstraint("temperature BETWEEN 0 AND 2", name="ck_ai_provider_configs_temperature"),
        sa.CheckConstraint("timeout_seconds > 0", name="ck_ai_provider_configs_timeout"),
        sa.CheckConstraint("max_retries >= 0", name="ck_ai_provider_configs_max_retries"),
        sa.UniqueConstraint("user_id", "name", name="uq_ai_provider_configs_user_id_name"),
    )
    op.create_table(
        "ai_call_logs",
        _id(), _user(),
        sa.Column("provider_config_id", pg.UUID(as_uuid=True), sa.ForeignKey("ai_provider_configs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("request_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _jsonb_obj("metadata"),
        _created(),
        sa.CheckConstraint("provider IN ('openai','deepseek','openai_compatible')", name="ck_ai_call_logs_provider"),
        sa.CheckConstraint("status IN ('pending','running','succeeded','failed','cancelled')", name="ck_ai_call_logs_status"),
    )

    # ---- 知识与生成内容 ----
    op.create_table(
        "knowledge_points",
        _id(), _user(),
        sa.Column("subject_id", pg.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.SmallInteger(), nullable=False),
        _jsonb_arr("keywords"),
        _jsonb_arr("tags"),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("merged_into_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("canonical_hash", sa.CHAR(64), nullable=False),
        sa.Column("manual_revision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        _version(), *_timestamps(),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_knowledge_points_difficulty"),
        sa.CheckConstraint("status IN ('draft','active','archived','merged')", name="ck_knowledge_points_status"),
    )
    op.create_table(
        "knowledge_point_sources",
        _id(), _user(),
        sa.Column("knowledge_point_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_note_id", pg.UUID(as_uuid=True), sa.ForeignKey("raw_notes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        _created(),
        sa.UniqueConstraint("knowledge_point_id", "raw_note_id", name="uq_knowledge_point_sources_kp_raw_note"),
    )
    op.create_table(
        "review_items",
        _id(), _user(),
        sa.Column("knowledge_point_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_type", sa.String(24), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("options", pg.JSONB(), nullable=True),
        sa.Column("item_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("manual_revision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider_config_id", pg.UUID(as_uuid=True), sa.ForeignKey("ai_provider_configs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("ai_call_log_id", pg.UUID(as_uuid=True), sa.ForeignKey("ai_call_logs.id", ondelete="RESTRICT"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("question_type IN ('qa','cloze','multiple_choice','short_explanation')", name="ck_review_items_question_type"),
        sa.CheckConstraint("item_version >= 1", name="ck_review_items_item_version"),
        sa.UniqueConstraint("knowledge_point_id", "question_type", "item_version", name="uq_review_items_kp_type_version"),
    )

    # ---- 调度、任务与历史 ----
    op.create_table(
        "schedule_states",
        _id(), _user(),
        sa.Column("knowledge_point_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("strategy", sa.String(20), nullable=False, server_default=sa.text("'ebbinghaus'")),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lapse_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("interval_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("interval_days", sa.Numeric(10, 3), nullable=True),
        sa.Column("stability", sa.Numeric(12, 6), nullable=True),
        sa.Column("difficulty", sa.Numeric(8, 6), nullable=True),
        sa.Column("retrievability", sa.Numeric(8, 6), nullable=True),
        sa.Column("target_retention", sa.Numeric(5, 4), nullable=True),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        _jsonb_obj("parameters"),
        _jsonb_obj("last_calculation"),
        sa.Column("strategy_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_timestamps(),
        sa.CheckConstraint("strategy IN ('ebbinghaus','fsrs')", name="ck_schedule_states_strategy"),
        sa.UniqueConstraint("knowledge_point_id", name="uq_schedule_states_knowledge_point_id"),
    )
    op.create_table(
        "daily_review_batches",
        _id(), _user(),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("subject_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        *_timestamps(),
        sa.CheckConstraint("status IN ('pending','ready','completed','cancelled')", name="ck_daily_review_batches_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_daily_review_batches_user_id_idempotency_key"),
    )
    op.create_table(
        "daily_review_tasks",
        _id(), _user(),
        sa.Column("batch_id", pg.UUID(as_uuid=True), sa.ForeignKey("daily_review_batches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("knowledge_point_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("review_item_id", pg.UUID(as_uuid=True), sa.ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("scheduled_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _version(), *_timestamps(),
        sa.CheckConstraint("status IN ('pending','in_progress','completed','skipped','cancelled')", name="ck_daily_review_tasks_status"),
        sa.UniqueConstraint("batch_id", "knowledge_point_id", name="uq_daily_review_tasks_batch_kp"),
    )
    op.create_table(
        "review_history",
        _id(), _user(),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("daily_review_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("knowledge_point_id", pg.UUID(as_uuid=True), sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("review_item_id", pg.UUID(as_uuid=True), sa.ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("strategy", sa.String(20), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("answer_self_assessment", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        _jsonb_obj("previous_schedule"),
        _jsonb_obj("result_schedule"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        _created(),
        sa.CheckConstraint("strategy IN ('ebbinghaus','fsrs')", name="ck_review_history_strategy"),
        sa.CheckConstraint("rating IN ('again','hard','good','easy')", name="ck_review_history_rating"),
        sa.CheckConstraint("duration_seconds >= 0", name="ck_review_history_duration_seconds"),
        sa.UniqueConstraint("task_id", name="uq_review_history_task_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_review_history_user_id_idempotency_key"),
    )

    # ---- 通知 ----
    op.create_table(
        "notification_channel_configs",
        _id(), _user(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column("credential_ref", sa.String(160), nullable=False),
        _jsonb_obj("settings"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _version(), *_timestamps(),
        sa.CheckConstraint(
            "channel_type IN ('wecom_app','wechat_official_account','third_party_push','wecom_webhook','dingtalk_webhook','dingtalk_app','smtp')",
            name="ck_channel_configs_channel_type",
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_channel_configs_user_id_name"),
    )
    op.create_table(
        "notification_templates",
        _id(), _user(),
        sa.Column("subject_id", pg.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column("template_key", sa.String(80), nullable=False),
        sa.Column("title_template", sa.Text(), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=False),
        _jsonb_arr("schema_variables"),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _version(), *_timestamps(),
        sa.CheckConstraint(
            "channel_type IN ('wecom_app','wechat_official_account','third_party_push','wecom_webhook','dingtalk_webhook','dingtalk_app','smtp')",
            name="ck_templates_channel_type",
        ),
        sa.UniqueConstraint(
            "user_id", "subject_id", "channel_type", "template_key", "version",
            name="uq_templates_user_subject_type_key_version",
        ),
    )
    op.create_table(
        "notification_jobs",
        _id(), _user(),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("daily_review_tasks.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel_config_id", pg.UUID(as_uuid=True), sa.ForeignKey("notification_channel_configs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", pg.UUID(as_uuid=True), sa.ForeignKey("notification_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("rendered_title", sa.Text(), nullable=True),
        sa.Column("rendered_body", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('pending','processing','sent','failed','cancelled')", name="ck_notification_jobs_status"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_notification_jobs_user_id_idempotency_key"),
    )
    op.create_table(
        "notification_deliveries",
        _id(), _user(),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("notification_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_message_id", sa.String(256), nullable=True),
        _jsonb_obj("request_metadata"),
        _jsonb_obj("response_metadata"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        _created(),
        sa.CheckConstraint("status IN ('sending','sent','failed')", name="ck_notification_deliveries_status"),
        sa.UniqueConstraint("job_id", "attempt_no", name="uq_notification_deliveries_job_attempt"),
    )

    # ---- 索引（含部分唯一 / GIN / NULLS NOT DISTINCT / DESC） ----
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_subjects_user_id_parent_id", "subjects", ["user_id", "parent_id"])
    op.create_index("ix_subjects_tags_gin", "subjects", ["tags"], postgresql_using="gin")
    op.create_index(
        "uq_subject_strategies_active_subject", "subject_strategies", ["subject_id"],
        unique=True, postgresql_where=sa.text("is_active"),
    )
    op.create_index("ix_subject_strategies_user_id_subject_id", "subject_strategies", ["user_id", "subject_id"])
    op.create_index("ix_notion_data_sources_enabled_next_sync", "notion_data_sources", ["is_enabled", "next_sync_at"])
    op.create_index("ix_sync_runs_source_created", "sync_runs", ["data_source_id", sa.text("created_at DESC")])
    op.create_index("ix_sync_runs_status_next_retry", "sync_runs", ["status", "next_retry_at"])
    op.create_index("ix_raw_notes_user_last_edited", "raw_notes", ["user_id", "last_edited_time"])
    op.create_index("ix_raw_notes_content_hash", "raw_notes", ["content_hash"])
    op.create_index(
        "uq_knowledge_points_user_canonical_hash", "knowledge_points", ["user_id", "canonical_hash"],
        unique=True, postgresql_where=sa.text("status <> 'merged'"),
    )
    op.create_index("ix_knowledge_points_user_subject_status", "knowledge_points", ["user_id", "subject_id", "status"])
    op.create_index("ix_knowledge_points_keywords_gin", "knowledge_points", ["keywords"], postgresql_using="gin")
    op.create_index("ix_knowledge_points_tags_gin", "knowledge_points", ["tags"], postgresql_using="gin")
    op.create_index("ix_knowledge_point_sources_raw_note_id", "knowledge_point_sources", ["raw_note_id"])
    op.create_index(
        "uq_review_items_current", "review_items", ["knowledge_point_id"],
        unique=True, postgresql_where=sa.text("is_current"),
    )
    op.create_index("ix_review_items_user_id", "review_items", ["user_id"])
    op.create_index("ix_schedule_states_user_due", "schedule_states", ["user_id", "due_at"])
    op.create_index("ix_schedule_states_strategy_due", "schedule_states", ["strategy", "due_at"])
    op.create_index(
        "uq_daily_review_batches_user_date_subject", "daily_review_batches",
        ["user_id", "local_date", "subject_id"], unique=True, postgresql_nulls_not_distinct=True,
    )
    op.create_index("ix_daily_review_tasks_user_status_due", "daily_review_tasks", ["user_id", "status", "scheduled_due_at"])
    op.create_index("ix_daily_review_tasks_batch_position", "daily_review_tasks", ["batch_id", "position"])
    op.create_index("ix_review_history_user_reviewed", "review_history", ["user_id", sa.text("reviewed_at DESC")])
    op.create_index("ix_review_history_kp_reviewed", "review_history", ["knowledge_point_id", sa.text("reviewed_at DESC")])
    op.create_index(
        "uq_channel_configs_default", "notification_channel_configs", ["user_id"],
        unique=True, postgresql_where=sa.text("is_default"),
    )
    op.create_index(
        "ix_channel_configs_user_type_enabled", "notification_channel_configs",
        ["user_id", "channel_type", "is_enabled"],
    )
    op.create_index(
        "ix_templates_active_lookup", "notification_templates",
        ["user_id", "channel_type", "template_key"], postgresql_where=sa.text("is_active"),
    )
    op.create_index("ix_notification_jobs_status_next_attempt", "notification_jobs", ["status", "next_attempt_at"])
    op.create_index("ix_notification_jobs_task_id", "notification_jobs", ["task_id"])
    op.create_index(
        "ix_notification_deliveries_user_attempted", "notification_deliveries",
        ["user_id", sa.text("attempted_at DESC")],
    )
    op.create_index(
        "uq_ai_provider_configs_default", "ai_provider_configs", ["user_id"],
        unique=True, postgresql_where=sa.text("is_default"),
    )
    op.create_index("ix_ai_call_logs_user_created", "ai_call_logs", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_ai_call_logs_status_created", "ai_call_logs", ["status", "created_at"])
    op.create_index("ix_ai_call_logs_request_id", "ai_call_logs", ["request_id"])


_TABLES_IN_CREATION_ORDER = [
    "users", "subjects", "subject_strategies",
    "notion_integrations", "notion_data_sources", "sync_runs", "raw_notes",
    "ai_provider_configs", "ai_call_logs",
    "knowledge_points", "knowledge_point_sources", "review_items",
    "schedule_states", "daily_review_batches", "daily_review_tasks", "review_history",
    "notification_channel_configs", "notification_templates", "notification_jobs",
    "notification_deliveries",
]


def downgrade() -> None:
    # 表上的索引随表删除一并消失；按反向依赖顺序删表。
    for table in reversed(_TABLES_IN_CREATION_ORDER):
        op.drop_table(table)
    # 扩展属于数据库级共享对象，不在此迁移中删除（避免影响其它 schema）。

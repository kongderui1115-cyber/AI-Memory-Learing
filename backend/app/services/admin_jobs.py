"""Read-only admin time series over persisted terminal processing records."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import Numeric, case, cast, extract, func, literal, null, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChapterJob, DailyReviewBatch, NotificationDelivery, SyncRun

KINDS = {
    "notion": "Notion 同步",
    "chapter": "章节处理",
    "review_batch": "复习任务生成",
    "notification": "通知投递尝试",
}


@dataclass
class Totals:
    success: int = 0
    failure: int = 0
    partial: int = 0
    duration_total_ms: float = 0
    duration_samples: int = 0

    def add(self, success, failure, partial, duration_ms, samples):
        self.success += success
        self.failure += failure
        self.partial += partial
        self.duration_total_ms += float(duration_ms or 0)
        self.duration_samples += samples

    def result(self):
        return {
            "success": self.success,
            "failure": self.failure,
            "partial": self.partial,
            "average_ms": self.duration_total_ms / self.duration_samples
            if self.duration_samples
            else None,
            "duration_samples": self.duration_samples,
        }


async def aggregate_jobs(
    session: AsyncSession,
    zone_name: str,
    first: datetime,
    last: datetime,
    start_date: date,
    end_date: date,
):
    def daily_rows(key, timestamp, status, successes, failures=(), partials=(), duration=None):
        local_day = func.date(func.timezone(zone_name, timestamp))
        return (
            select(
                literal(key).label("kind"),
                local_day.label("date"),
                func.count().filter(status.in_(successes)).label("success"),
                (func.count().filter(status.in_(failures)) if failures else literal(0)).label(
                    "failure"
                ),
                (func.count().filter(status.in_(partials)) if partials else literal(0)).label(
                    "partial"
                ),
                (func.sum(duration) if duration is not None else cast(null(), Numeric)).label(
                    "duration_ms"
                ),
                (func.count(duration) if duration is not None else literal(0)).label(
                    "duration_samples"
                ),
            )
            .where(
                timestamp >= first, timestamp < last, status.in_(successes + failures + partials)
            )
            .group_by(local_day)
        )

    # A chapter row shows the latest terminal state for one revision. There is no
    # per-attempt timing or immutable completion timestamp on that table.
    notion_duration = case(
        (
            SyncRun.finished_at >= SyncRun.started_at,
            extract("epoch", SyncRun.finished_at - SyncRun.started_at) * 1000,
        )
    )
    notification_duration = case(
        (NotificationDelivery.duration_ms >= 0, NotificationDelivery.duration_ms)
    )
    statement = union_all(
        daily_rows(
            "notion",
            SyncRun.finished_at,
            SyncRun.status,
            ("succeeded",),
            ("failed",),
            ("partial",),
            notion_duration,
        ),
        daily_rows(
            "chapter",
            ChapterJob.updated_at,
            ChapterJob.status,
            ("succeeded",),
            ("failed",),
        ),
        daily_rows(
            "review_batch",
            DailyReviewBatch.generated_at,
            DailyReviewBatch.status,
            ("ready", "completed"),
        ),
        daily_rows(
            "notification",
            NotificationDelivery.attempted_at,
            NotificationDelivery.status,
            ("sent",),
            ("failed",),
            duration=notification_duration,
        ),
    )
    by_kind = {key: Totals() for key in KINDS}
    by_day = {
        start_date + timedelta(days=offset): Totals()
        for offset in range((end_date - start_date).days + 1)
    }
    for kind, day, *counts in await session.execute(statement):
        by_kind[kind].add(*counts)
        by_day[day].add(*counts)
    return {
        "kinds": [
            {"key": key, "name": name, **by_kind[key].result()} for key, name in KINDS.items()
        ],
        "days": [{"date": day, **totals.result()} for day, totals in by_day.items()],
    }

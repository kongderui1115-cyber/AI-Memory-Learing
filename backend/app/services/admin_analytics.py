"""Read-only administrator aggregates from learner and background records."""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, text

from app.domain import memory, scheduling
from app.models import (
    AICallLog,
    ChapterJob,
    DailyReviewBatch,
    DailyReviewTask,
    KnowledgePoint,
    NotificationJob,
    ReviewHistory,
    ScheduleState,
    StudySession,
    Subject,
    SyncRun,
)
from app.services.accounts import audit
from app.services.admin import staff
from app.services.admin_jobs import aggregate_jobs
from app.services.common import ServiceError, utcnow
from app.services.insights import bounds
from app.services.review_workload import OPEN_TASK_STATUSES

RECALLED = ("good", "easy")
STAGES = (0, 1, 3, 7, 14, 21, 30)


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


async def count_events(session, timestamp, zone_name, first, last):
    day = func.date(func.timezone(zone_name, timestamp)).label("day")
    rows = await session.execute(
        select(day, func.count())
        .where(timestamp >= first, timestamp < last)
        .group_by(day)
    )
    return dict(rows.all())


async def study_totals(session, zone, first, last):
    totals = defaultdict(timedelta)
    rows = await session.stream(
        select(StudySession.started_at, StudySession.ended_at)
        .where(StudySession.ended_at > first, StudySession.started_at < last)
        .execution_options(yield_per=500)
    )
    try:
        async for started, ended in rows:
            lower = max(first, started).astimezone(timezone.utc)
            upper = min(last, ended).astimezone(timezone.utc)
            day = lower.astimezone(zone).date()
            while lower < upper:
                end_of_day = bounds(day, zone)[1].astimezone(timezone.utc)
                totals[day] += max(timedelta(), min(upper, end_of_day) - lower)
                lower = max(lower, end_of_day)
                day += timedelta(days=1)
    finally:
        await rows.close()
    return {day: int(value.total_seconds()) for day, value in totals.items()}


def task_counts(group, start, end):
    return (
        select(group, func.count(), func.count().filter(DailyReviewTask.status == "completed"))
        .select_from(DailyReviewTask)
        .join(DailyReviewBatch, DailyReviewBatch.id == DailyReviewTask.batch_id)
        .where(DailyReviewBatch.local_date.between(start, end), DailyReviewTask.status != "cancelled")
        .group_by(group)
    )


async def learning_activity(session, zone, start, end, first, last):
    created = await count_events(session, KnowledgePoint.created_at, zone.key, first, last)
    reviews = await count_events(session, ReviewHistory.reviewed_at, zone.key, first, last)
    studies = await study_totals(session, zone, first, last)
    batches = {
        day: (assigned, done)
        for day, assigned, done in await session.execute(
            task_counts(DailyReviewBatch.local_date, start, end)
        )
    }
    result = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        assigned, done = batches.get(day, (0, 0))
        result.append({
            "date": day,
            "knowledge": created.get(day, 0),
            "study_seconds": studies.get(day, 0),
            "reviews": reviews.get(day, 0),
            "assigned": assigned,
            "completed": done,
            "completion_rate": fraction(done, assigned),
        })
    return result


async def due_total(session, now):
    open_task = exists(
        select(DailyReviewTask.id).where(
            DailyReviewTask.user_id == KnowledgePoint.user_id,
            DailyReviewTask.knowledge_point_id == KnowledgePoint.id,
            DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
        )
    )
    unqueued = (
        select(func.count()).select_from(ScheduleState)
        .join(KnowledgePoint, KnowledgePoint.id == ScheduleState.knowledge_point_id)
        .where(KnowledgePoint.status == "active", ScheduleState.due_at <= now, ~open_task)
        .scalar_subquery()
    )
    return await session.scalar(
        select(func.count() + unqueued).select_from(DailyReviewTask)
        .where(DailyReviewTask.status.in_(OPEN_TASK_STATUSES))
    )


async def subject_activity(session, start, end, first, last):
    count = func.count(KnowledgePoint.id)
    subjects = (
        await session.execute(
            select(Subject.id, Subject.name, count)
            .outerjoin(KnowledgePoint, (KnowledgePoint.subject_id == Subject.id)
                       & (KnowledgePoint.status == "active"))
            .where(Subject.is_active)
            .group_by(Subject.id, Subject.name)
            .order_by(count.desc(), Subject.name, Subject.id)
            .limit(12)
        )
    ).all()
    ids = [subject.id for subject in subjects]
    if not ids:
        return []
    tasks = {
        subject_id: (assigned, done)
        for subject_id, assigned, done in await session.execute(
            task_counts(KnowledgePoint.subject_id, start, end)
            .join(KnowledgePoint, KnowledgePoint.id == DailyReviewTask.knowledge_point_id)
            .where(KnowledgePoint.subject_id.in_(ids))
        )
    }
    ranked = (
        select(
            KnowledgePoint.subject_id,
            KnowledgePoint.status,
            ReviewHistory.rating,
            func.row_number().over(
                partition_by=ReviewHistory.knowledge_point_id,
                order_by=(ReviewHistory.reviewed_at.desc(), ReviewHistory.id.desc()),
            ).label("rank"),
        )
        .join(KnowledgePoint, KnowledgePoint.id == ReviewHistory.knowledge_point_id)
        .where(KnowledgePoint.subject_id.in_(ids), ReviewHistory.reviewed_at >= first,
               ReviewHistory.reviewed_at < last)
        .subquery()
    )
    current_rating = (ranked.c.rank == 1) & (ranked.c.status == "active")
    reviews = {
        subject_id: (total, recalled, active_sampled, weak)
        for subject_id, total, recalled, active_sampled, weak in await session.execute(
            select(
                ranked.c.subject_id,
                func.count(),
                func.count().filter(ranked.c.rating.in_(RECALLED)),
                func.count().filter(current_rating),
                func.count().filter(current_rating & ranked.c.rating.in_(("again", "hard"))),
            ).group_by(ranked.c.subject_id)
        )
    }
    results = []
    for subject_id, name, knowledge in subjects:
        assigned, done = tasks.get(subject_id, (0, 0))
        sampled, recalled, active_sampled, weak = reviews.get(subject_id, (0, 0, 0, 0))
        results.append({
            "id": subject_id,
            "name": name,
            "knowledge": knowledge,
            "assigned": assigned,
            "completed": done,
            "completion_rate": fraction(done, assigned),
            "reviews": sampled,
            "recall_rate": fraction(recalled, sampled),
            "weak": weak if active_sampled else None,
        })
    return results


@dataclass
class RetentionBucket:
    observed_samples: int = 0
    recalled: int = 0
    predicted_samples: int = 0
    predicted_sum: float = 0.0
    prediction_versions: set[str] = field(default_factory=set)

    def add(self, rating, estimate, version):
        self.observed_samples += 1
        self.recalled += rating in RECALLED
        if estimate is not None:
            self.predicted_samples += 1
            self.predicted_sum += estimate
            self.prediction_versions.add(version)

    def result(self):
        return {
            "observed_samples": self.observed_samples,
            "observed": fraction(self.recalled, self.observed_samples),
            "predicted_samples": self.predicted_samples,
            "predicted": fraction(self.predicted_sum, self.predicted_samples),
            "prediction_versions": sorted(self.prediction_versions),
        }


def retention_sample(previous, reviewed_at):
    if not isinstance(previous, dict) or not isinstance(previous.get("last_reviewed_at"), str):
        return None
    try:
        prior = datetime.fromisoformat(previous["last_reviewed_at"])
    except ValueError:
        return None
    if prior.utcoffset() is None or prior > reviewed_at:
        return None
    stage = STAGES[bisect_right(STAGES, (reviewed_at - prior).days) - 1]
    try:
        state = scheduling.from_mapping(previous)
        estimated = memory.retrievability_at(state, reviewed_at)
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        # Older or incomplete snapshots still contribute to the observed cohort.
        return stage, None, ""
    return stage, estimated, state.algorithm_version


async def retention_activity(session, subjects, first, last):
    names = {None: "全部学科", **{row["id"]: row["name"] for row in subjects}}
    buckets = defaultdict(RetentionBucket)
    rows = await session.stream(
        select(KnowledgePoint.subject_id, ReviewHistory.reviewed_at, ReviewHistory.rating,
               ReviewHistory.previous_schedule)
        .join(KnowledgePoint, KnowledgePoint.id == ReviewHistory.knowledge_point_id)
        .where(ReviewHistory.strategy == "fsrs", ReviewHistory.reviewed_at >= first,
               ReviewHistory.reviewed_at < last)
        .execution_options(yield_per=500)
    )
    try:
        async for subject_id, reviewed_at, rating, previous in rows:
            sample = retention_sample(previous, reviewed_at)
            if sample is None:
                continue
            stage, estimate, version = sample
            buckets[None, stage].add(rating, estimate, version)
            if subject_id in names:
                buckets[subject_id, stage].add(rating, estimate, version)
    finally:
        await rows.close()
    return [
        {"stage": f"D{stage}", "subject_id": subject_id, "subject_name": name,
         **buckets[subject_id, stage].result()}
        for subject_id, name in names.items()
        for stage in STAGES
    ]


async def ai_usage(session, zone, start, end, first, last):
    day = func.date(func.timezone(zone.key, AICallLog.created_at)).label("day")
    window = (AICallLog.created_at >= first, AICallLog.created_at < last)
    valid_tokens = AICallLog.total_tokens >= 0
    terminal = AICallLog.status.in_(("succeeded", "failed"))
    rows = await session.execute(
        select(
            day, func.count(), func.count().filter(terminal),
            func.count().filter(AICallLog.status == "failed"),
            func.sum(AICallLog.total_tokens).filter(valid_tokens),
            func.count().filter(valid_tokens),
        ).where(*window).group_by(day)
    )
    daily = {key: (calls, ended, errors, tokens, samples)
             for key, calls, ended, errors, tokens, samples in rows}
    timeline = []
    for offset in range((end - start).days + 1):
        key = start + timedelta(days=offset)
        calls, ended, errors, tokens, samples = daily.get(key, (0, 0, 0, None, 0))
        timeline.append({
            "date": key, "calls": calls, "terminal_calls": ended, "errors": errors,
            "tokens": tokens, "token_samples": samples,
        })

    async def breakdown(label):
        count = func.count()
        items = await session.execute(
            select(label, count).where(*window).group_by(label).order_by(count.desc(), label).limit(20)
        )
        return [{"name": name, "value": value} for name, value in items]

    return {
        "days": timeline,
        "models": await breakdown(func.concat(AICallLog.provider, " / ", AICallLog.model_name)),
        "tasks": await breakdown(AICallLog.operation),
    }


async def workflow_counts(session, first, last):
    result = {
        "imported_versions": await session.scalar(
            select(func.coalesce(func.sum(SyncRun.items_imported), 0)).where(
                SyncRun.status.in_(("succeeded", "partial")),
                SyncRun.finished_at >= first, SyncRun.finished_at < last,
            )
        ),
        "generated_points": await session.scalar(
            select(func.count()).select_from(KnowledgePoint).where(
                KnowledgePoint.source_generated_at >= first, KnowledgePoint.source_generated_at < last,
            )
        ),
    }
    for key, model, statuses in (
        ("sync_queued", SyncRun, ("pending", "running")),
        ("extraction_queued", ChapterJob, ("pending", "running")),
        ("extraction_blocked", ChapterJob, ("blocked",)),
        ("notification_queued", NotificationJob, ("pending", "processing")),
    ):
        result[key] = await session.scalar(
            select(func.count()).select_from(model).where(model.status.in_(statuses))
        )
    return result


async def analytics(db, actor, ip, request_id, days, from_date, to_date):
    now = utcnow()
    async with db.transaction() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        user = await staff(session, actor)
        zone = ZoneInfo(user.timezone)
        today = now.astimezone(zone).date()
        end = to_date or today
        start = from_date or end - timedelta(days=min(days - 1, end.toordinal() - 1))
        if start.year < 1970 or end.year > 9998 or not 0 <= (end - start).days < 366:
            raise ServiceError("VALIDATION_ERROR", "统计区间须为 1970 至 9998 年的连续日期，最多 366 天")
        first = bounds(start, zone)[0].astimezone(timezone.utc)
        last = min(bounds(end, zone)[1].astimezone(timezone.utc), now)
        today_start = bounds(today, zone)[0]
        subjects = await subject_activity(session, start, end, first, last)
        result = {
            "as_of": now,
            "timezone": zone.key,
            "from_date": start,
            "to_date": end,
            "today_due": await due_total(session, now),
            "today_ai_calls": await session.scalar(
                select(func.count()).select_from(AICallLog)
                .where(AICallLog.created_at >= today_start, AICallLog.created_at < now)
            ),
            "learning": await learning_activity(session, zone, start, end, first, last),
            "subjects": subjects,
            "retention": await retention_activity(session, subjects, first, last),
            "jobs": await aggregate_jobs(session, zone.key, first, last, start, end),
            "ai_usage": await ai_usage(session, zone, start, end, first, last),
            "workflow": await workflow_counts(session, first, last),
        }
        audit(session, user, "admin_analytics_read", "system-analytics", "allowed", ip, request_id)
        return result

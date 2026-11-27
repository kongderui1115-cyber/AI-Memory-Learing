"""Real learning activity and schedule projections; no synthetic dashboard values."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, union

from app.models import (
    Chapter,
    DailyReviewBatch,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ScheduleState,
    StudySession,
    Subject,
    User,
)
from app.services.common import ServiceError, utcnow


def bounds(day, zone):
    return datetime.combine(day, time.min, zone), datetime.combine(
        day + timedelta(days=1), time.min, zone
    )


async def overview(db, user_id, days=14, from_date=None, to_date=None):
    async with db.transaction() as session:
        user = await session.get(User, user_id)
        zone = ZoneInfo(user.timezone)
        now = utcnow()
        today = now.astimezone(zone).date()
        end = to_date or today
        try:
            start = from_date or end - timedelta(days=days - 1)
        except OverflowError:
            raise ServiceError("VALIDATION_ERROR", "统计日期超出支持范围") from None
        if start.year < 1970 or end.year > 9998:
            raise ServiceError("VALIDATION_ERROR", "统计日期应在1970至9998年之间")
        if start > end or (end - start).days >= 366:
            raise ServiceError("VALIDATION_ERROR", "统计范围应为连续且不超过366天")
        first, last = bounds(start, zone)[0], bounds(end, zone)[1]
        today_start, today_end = bounds(today, zone)
        history_day = func.date(func.timezone(user.timezone, ReviewHistory.reviewed_at))
        history_rows = (
            await session.execute(
                select(
                    history_day,
                    func.count(),
                    func.coalesce(func.sum(ReviewHistory.duration_seconds), 0),
                    func.count().filter(ReviewHistory.rating.in_(["good", "easy"])),
                )
                .where(
                    ReviewHistory.user_id == user_id,
                    or_(
                        (ReviewHistory.reviewed_at >= first) & (ReviewHistory.reviewed_at < last),
                        (ReviewHistory.reviewed_at >= today_start)
                        & (ReviewHistory.reviewed_at < today_end),
                    ),
                )
                .group_by(history_day)
            )
        ).all()
        history = {
            day: (count, int(seconds), recalled) for day, count, seconds, recalled in history_rows
        }
        studies = (
            await session.execute(
                select(StudySession.started_at, StudySession.ended_at).where(
                    StudySession.user_id == user_id,
                    or_(
                        (StudySession.ended_at > first) & (StudySession.started_at < last),
                        (StudySession.ended_at > today_start)
                        & (StudySession.started_at < today_end),
                    ),
                )
            )
        ).all()

        def activity(day):
            lower, upper = bounds(day, zone)
            # Timestamp arithmetic preserves actual elapsed seconds across DST transitions.
            seconds = sum(
                max(
                    0, min(b.timestamp(), upper.timestamp()) - max(a.timestamp(), lower.timestamp())
                )
                for a, b in studies
            )
            count, review_seconds, recalled = history.get(day, (0, 0, 0))
            return {
                "date": day,
                "study_seconds": int(seconds),
                "review_seconds": review_seconds,
                "reviews": count,
                "recalled": recalled,
            }

        timeline = [activity(start + timedelta(days=i)) for i in range((end - start).days + 1)]
        current = activity(today)
        chapter_rows = (
            await session.execute(
                select(
                    Chapter.subject_id,
                    func.count(),
                    func.count().filter(Chapter.status == "completed"),
                )
                .where(Chapter.user_id == user_id)
                .group_by(Chapter.subject_id)
            )
        ).all()
        chapters = {subject: (total, completed) for subject, total, completed in chapter_rows}
        knowledge_rows = (
            await session.execute(
                select(KnowledgePoint.subject_id, func.count())
                .where(KnowledgePoint.user_id == user_id, KnowledgePoint.status == "active")
                .group_by(KnowledgePoint.subject_id)
            )
        ).all()
        knowledge = dict(knowledge_rows)
        subjects = (
            await session.scalars(
                select(Subject)
                .where(Subject.user_id == user_id, Subject.is_active.is_(True))
                .order_by(Subject.created_at)
            )
        ).all()
        task_today = DailyReviewBatch.local_date == today
        pending = DailyReviewTask.status.in_(["pending", "in_progress"])
        task_counts = (
            await session.execute(
                select(
                    func.count().filter(task_today),
                    func.count().filter(task_today & (DailyReviewTask.status == "completed")),
                    func.count().filter(pending),
                    func.count().filter(pending & (DailyReviewTask.scheduled_due_at < now)),
                )
                .select_from(DailyReviewTask)
                .join(DailyReviewBatch, DailyReviewBatch.id == DailyReviewTask.batch_id)
                .where(DailyReviewTask.user_id == user_id)
            )
        ).one()
        review_total = await session.scalar(
            select(func.count()).select_from(ReviewHistory).where(ReviewHistory.user_id == user_id)
        )
        # A learning day is a local date on which a study session ended or a review was submitted.
        study_day = func.date(func.timezone(user.timezone, StudySession.ended_at))
        active_dates = set(
            (
                await session.scalars(
                    union(
                        select(study_day).where(
                            StudySession.user_id == user_id, StudySession.duration_seconds > 0
                        ),
                        select(history_day).where(ReviewHistory.user_id == user_id),
                    )
                )
            ).all()
        )
        streak, day = 0, today if today in active_dates else today - timedelta(days=1)
        while day in active_dates:
            streak += 1
            day -= timedelta(days=1)
        state_rows = (
            await session.execute(
                select(ScheduleState.review_count, func.count())
                .join(KnowledgePoint, KnowledgePoint.id == ScheduleState.knowledge_point_id)
                .where(ScheduleState.user_id == user_id, KnowledgePoint.status == "active")
                .group_by(ScheduleState.review_count)
            )
        ).all()
        memory = [
            {"key": "new", "name": "尚未复习", "count": sum(n for r, n in state_rows if r == 0)},
            {
                "key": "building",
                "name": "开始巩固 · 1–2次",
                "count": sum(n for r, n in state_rows if 1 <= r < 3),
            },
            {
                "key": "growing",
                "name": "持续复习 · 3次以上",
                "count": sum(n for r, n in state_rows if r >= 3),
            },
        ]
        schedule_day = func.date(func.timezone(user.timezone, ScheduleState.due_at))
        schedule_rows = (
            await session.execute(
                select(
                    schedule_day,
                    func.count(),
                    func.count().filter(ScheduleState.strategy == "fsrs"),
                )
                .join(KnowledgePoint, KnowledgePoint.id == ScheduleState.knowledge_point_id)
                .where(
                    ScheduleState.user_id == user_id,
                    KnowledgePoint.status == "active",
                    or_(
                        schedule_day.between(start, end),
                        schedule_day.between(today, today + timedelta(days=30)),
                    ),
                )
                .group_by(schedule_day)
                .order_by(schedule_day)
            )
        ).all()
        plans = [
            {"date": day, "count": count, "fsrs": fsrs, "ebbinghaus": count - fsrs}
            for day, count, fsrs in schedule_rows
        ]
        reviewed = sum(item["reviews"] for item in timeline)
        return {
            "timezone": user.timezone,
            "today": today,
            "from_date": start,
            "to_date": end,
            "metrics": {
                "knowledge_total": sum(knowledge.values()),
                "chapter_total": sum(n for n, _ in chapters.values()),
                "chapter_completed": sum(n for _, n in chapters.values()),
                "today_study_seconds": current["study_seconds"],
                "today_review_seconds": current["review_seconds"],
                "today_reviews": current["reviews"],
                "today_tasks": task_counts[0],
                "today_completed_tasks": task_counts[1],
                "pending_reviews": task_counts[2],
                "overdue_reviews": task_counts[3],
                "learning_days": len(active_dates),
                "streak_days": streak,
                "recall_rate": sum(item["recalled"] for item in timeline) / reviewed
                if reviewed
                else None,
                "review_total": review_total,
            },
            "activity": timeline,
            "subjects": [
                {
                    "id": s.id,
                    "name": s.name,
                    "knowledge_count": knowledge.get(s.id, 0),
                    "chapter_count": chapters.get(s.id, (0, 0))[0],
                    "completed_chapters": chapters.get(s.id, (0, 0))[1],
                }
                for s in subjects
            ],
            "memory": memory,
            "scheduled": [p for p in plans if start <= p["date"] <= end],
            "upcoming": [p for p in plans if today <= p["date"] <= today + timedelta(days=30)],
        }

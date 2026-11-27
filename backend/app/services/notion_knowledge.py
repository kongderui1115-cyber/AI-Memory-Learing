"""Reconcile generated knowledge with an immutable Notion revision."""

from collections import defaultdict

from sqlalchemy import exists, select, update

from app.models import DailyReviewBatch, DailyReviewTask, KnowledgePoint, KnowledgePointSource, RawNote, ReviewItem
from app.services.review_workload import OPEN_TASK_STATUSES


async def revision_points(session, chapter, raw):
    rows = (
        await session.execute(
            select(KnowledgePoint, KnowledgePointSource.source_excerpt, RawNote.id, RawNote.external_page_id)
            .join(KnowledgePointSource, KnowledgePointSource.knowledge_point_id == KnowledgePoint.id)
            .join(RawNote, RawNote.id == KnowledgePointSource.raw_note_id)
            .where(
                KnowledgePoint.user_id == chapter.user_id,
                KnowledgePoint.chapter_id == chapter.id,
                KnowledgePoint.status.in_(("active", "draft")),
                KnowledgePoint.source_generated_at.is_not(None),
                KnowledgePointSource.user_id == chapter.user_id,
                RawNote.user_id == chapter.user_id,
            )
        )
    ).all()
    shared = {point.id for point, _, _, page_id in rows if page_id != raw.external_page_id}
    current = {point.id for point, _, raw_id, _ in rows if raw_id == raw.id}
    anchors = defaultdict(dict)
    stale = {}
    for point, quote, _, _ in rows:
        if point.id in shared:
            continue
        if quote:
            anchors[quote][point.id] = point
        if point.id not in current and point.status == "active" and not point.manual_revision:
            stale[point.id] = point
    return anchors, stale


async def hold_missing_points(session, user_id, candidates, refreshed_ids):
    missing = set(candidates).difference(refreshed_ids)
    if not missing:
        return []
    manually_curated = await session.scalars(
        select(ReviewItem.knowledge_point_id).where(
            ReviewItem.user_id == user_id, ReviewItem.knowledge_point_id.in_(missing),
            ReviewItem.is_current.is_(True), ReviewItem.manual_revision.is_(True),
        )
    )
    missing.difference_update(manually_curated)
    if not missing:
        return []
    for point_id in missing:
        point = candidates[point_id]
        point.status = "draft"
        point.version += 1
    batches = await session.scalars(
        update(DailyReviewTask)
        .where(
            DailyReviewTask.user_id == user_id,
            DailyReviewTask.knowledge_point_id.in_(missing),
            DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
        )
        .values(
            status="cancelled", skip_reason="source_needs_review",
            version=DailyReviewTask.version + 1,
        )
        .returning(DailyReviewTask.batch_id)
    )
    batch_ids = set(batches)
    if batch_ids:
        await session.execute(
            update(DailyReviewBatch)
            .where(
                DailyReviewBatch.user_id == user_id, DailyReviewBatch.id.in_(batch_ids),
                DailyReviewBatch.status.in_(("pending", "ready")),
                ~exists().where(
                    DailyReviewTask.batch_id == DailyReviewBatch.id,
                    DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
                ),
            )
            .values(status="completed", version=DailyReviewBatch.version + 1)
        )
    return sorted(str(point_id) for point_id in missing)

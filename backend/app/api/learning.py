"""Authenticated learning API using persistent services."""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response

from app.api.dependencies import current_user, database, expected_version, idempotency_key
from app.contracts.core import (
    ChapterJobRead,
    ChapterRead,
    ChapterUpdate,
    ChapterWrite,
    KnowledgeRead,
    KnowledgeUpdate,
    KnowledgeWrite,
    StudySessionRead,
    StudySessionWrite,
    SubjectUpdate,
    TaskDeferRequest,
    TaskSkipRequest,
)
from app.contracts.models import (
    DailyBatchRead,
    DailyGenerateRequest,
    DailyTaskRead,
    Page,
    ReviewCompleteRequest,
    ReviewCompleteResponse,
    ReviewHistoryRead,
    ReviewItemRead,
    ReviewItemWrite,
    ScheduleStateRead,
    ScheduleSwitchRequest,
    SubjectRead,
    SubjectWrite,
)
from app.models import (
    Chapter,
    ChapterJob,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ReviewItem,
    StudySession,
    Subject,
)
from app.services import learning
from app.services.reviews import complete_review

router = APIRouter(tags=["learning"])
Limit = Query(default=20, ge=1, le=100)


@router.get("/subjects", response_model=Page[SubjectRead])
async def subjects(
    limit: int = Limit,
    cursor: str | None = None,
    is_active: bool | None = None,
    parent_id: UUID | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    filters = []
    if is_active is not None:
        filters.append(Subject.is_active == is_active)
    if parent_id is not None:
        filters.append(Subject.parent_id == parent_id)
    return await learning.list_resources(
        db, actor.user_id, Subject, SubjectRead, limit=limit, cursor=cursor, filters=filters
    )


@router.post("/subjects", response_model=SubjectRead, status_code=201)
async def subject_create(
    body: SubjectWrite,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.create_subject(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/subjects/{resource_id}", response_model=SubjectRead)
async def subject(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_resource(db, actor.user_id, Subject, resource_id, SubjectRead)


@router.patch("/subjects/{resource_id}", response_model=SubjectRead)
async def subject_update(
    resource_id: UUID,
    body: SubjectUpdate,
    actor=Depends(current_user),
    db=Depends(database),
    version=Depends(expected_version),
):
    return await learning.update_subject(db, actor.user_id, resource_id, body, version)


@router.delete("/subjects/{resource_id}", status_code=204)
async def subject_disable(
    resource_id: UUID,
    actor=Depends(current_user),
    db=Depends(database),
    version=Depends(expected_version),
):
    await learning.update_subject(
        db, actor.user_id, resource_id, SubjectUpdate(is_active=False), version
    )
    return Response(status_code=204)


@router.get("/chapters", response_model=Page[ChapterRead])
async def chapters(
    limit: int = Limit,
    cursor: str | None = None,
    subject_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(not_started|in_progress|completed)$"),
    q: str | None = Query(default=None, max_length=200),
    actor=Depends(current_user),
    db=Depends(database),
):
    filters = []
    if subject_id:
        filters.append(Chapter.subject_id == subject_id)
    if status:
        filters.append(Chapter.status == status)
    if q:
        filters.append(Chapter.title.ilike(f"%{q}%"))
    return await learning.list_resources(
        db, actor.user_id, Chapter, ChapterRead, limit=limit, cursor=cursor, filters=filters
    )


@router.post("/chapters", response_model=ChapterRead, status_code=201)
async def chapter_create(
    body: ChapterWrite,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.create_chapter(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/chapters/{resource_id}", response_model=ChapterRead)
async def chapter(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_resource(db, actor.user_id, Chapter, resource_id, ChapterRead)


@router.patch("/chapters/{resource_id}", response_model=ChapterRead)
async def chapter_update(
    resource_id: UUID,
    body: ChapterUpdate,
    actor=Depends(current_user),
    db=Depends(database),
    version=Depends(expected_version),
):
    return await learning.update_chapter(db, actor.user_id, resource_id, body, version)


@router.post("/chapters/{resource_id}/complete", response_model=ChapterRead)
async def chapter_complete(
    resource_id: UUID,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.complete_chapter(
        db, request.app.state.settings, actor.user_id, resource_id, key
    )


@router.get("/chapters/{resource_id}/study-sessions", response_model=Page[StudySessionRead])
async def study_sessions(
    resource_id: UUID,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    await learning.get_resource(db, actor.user_id, Chapter, resource_id, ChapterRead)
    return await learning.list_resources(
        db,
        actor.user_id,
        StudySession,
        StudySessionRead,
        limit=limit,
        cursor=cursor,
        filters=[StudySession.chapter_id == resource_id],
    )


@router.post(
    "/chapters/{resource_id}/study-sessions", response_model=StudySessionRead, status_code=201
)
async def study_create(
    resource_id: UUID,
    body: StudySessionWrite,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.add_study_session(
        db, request.app.state.settings, actor.user_id, resource_id, body, key
    )


@router.get("/chapters/{resource_id}/jobs", response_model=Page[ChapterJobRead])
async def chapter_jobs(
    resource_id: UUID,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    await learning.get_resource(db, actor.user_id, Chapter, resource_id, ChapterRead)
    return await learning.list_resources(
        db,
        actor.user_id,
        ChapterJob,
        ChapterJobRead,
        limit=limit,
        cursor=cursor,
        filters=[ChapterJob.chapter_id == resource_id],
    )


@router.get("/knowledge-points", response_model=Page[KnowledgeRead])
async def knowledge(
    limit: int = Limit,
    cursor: str | None = None,
    subject_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(draft|active|archived|merged)$"),
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    filters = []
    if subject_id:
        filters.append(KnowledgePoint.subject_id == subject_id)
    if status:
        filters.append(KnowledgePoint.status == status)
    if q:
        filters.append(KnowledgePoint.title.ilike(f"%{q}%"))
    if tag:
        filters.append(KnowledgePoint.tags.contains([tag]))
    return await learning.list_knowledge(
        db, actor.user_id, limit=limit, cursor=cursor, filters=filters
    )


@router.post("/knowledge-points", response_model=KnowledgeRead, status_code=201)
async def knowledge_create(
    body: KnowledgeWrite,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.create_knowledge(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/knowledge-points/{resource_id}", response_model=KnowledgeRead)
async def knowledge_get(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_knowledge(db, actor.user_id, resource_id)


@router.patch("/knowledge-points/{resource_id}", response_model=KnowledgeRead)
async def knowledge_update(
    resource_id: UUID,
    body: KnowledgeUpdate,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    version=Depends(expected_version),
):
    return await learning.update_knowledge(
        db, request.app.state.settings, actor.user_id, resource_id, body, version
    )


@router.post("/knowledge-points/{resource_id}/activate", response_model=KnowledgeRead)
async def knowledge_activate(
    resource_id: UUID,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.activate_knowledge(
        db, request.app.state.settings, actor.user_id, resource_id, key
    )


@router.post("/knowledge-points/{resource_id}/archive", response_model=KnowledgeRead)
async def knowledge_archive(
    resource_id: UUID,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.activate_knowledge(
        db, request.app.state.settings, actor.user_id, resource_id, key, archive=True
    )


@router.get("/knowledge-points/{resource_id}/review-items", response_model=Page[ReviewItemRead])
async def review_items(
    resource_id: UUID,
    current_only: bool = True,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    await learning.get_knowledge(db, actor.user_id, resource_id)
    filters = [ReviewItem.knowledge_point_id == resource_id]
    if current_only:
        filters.append(ReviewItem.is_current.is_(True))
    return await learning.list_resources(
        db, actor.user_id, ReviewItem, ReviewItemRead, limit=limit, cursor=cursor, filters=filters
    )


@router.post(
    "/knowledge-points/{resource_id}/review-items", response_model=ReviewItemRead, status_code=201
)
async def review_item_create(
    resource_id: UUID,
    body: ReviewItemWrite,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.create_review_item(
        db, request.app.state.settings, actor.user_id, resource_id, body, key
    )


@router.get("/knowledge-points/{resource_id}/schedule", response_model=ScheduleStateRead)
async def schedule_get(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_schedule(db, actor.user_id, resource_id)


@router.post("/review-batches/generate", response_model=DailyBatchRead, status_code=201)
async def batch_generate(
    body: DailyGenerateRequest,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.generate_batch(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/review-batches", response_model=Page[DailyBatchRead])
async def batches(
    limit: int = Limit,
    cursor: str | None = None,
    local_date: date | None = None,
    status: str | None = None,
    subject_id: UUID | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    return await learning.list_batches(
        db, actor.user_id, limit, cursor, local_date, status, subject_id
    )


@router.get("/review-batches/{resource_id}", response_model=DailyBatchRead)
async def batch_get(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_batch(db, actor.user_id, resource_id)


@router.get("/review-tasks", response_model=Page[DailyTaskRead])
async def tasks(
    limit: int = Limit,
    cursor: str | None = None,
    status: str | None = None,
    local_date: date | None = None,
    subject_id: UUID | None = None,
    overdue: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    actor=Depends(current_user),
    db=Depends(database),
):
    return await learning.list_tasks(
        db, actor.user_id, limit, cursor, status, local_date, subject_id, overdue, q
    )


@router.get("/review-tasks/{resource_id}", response_model=DailyTaskRead)
async def task_get(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_resource(
        db, actor.user_id, DailyReviewTask, resource_id, DailyTaskRead
    )


@router.get("/review-tasks/{resource_id}/content")
async def task_content(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.task_content(db, actor.user_id, resource_id)


@router.post("/review-tasks/{resource_id}/start", response_model=DailyTaskRead)
async def task_start(
    resource_id: UUID,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.task_action(
        db, request.app.state.settings, actor.user_id, resource_id, key, "start"
    )


@router.post("/review-tasks/{resource_id}/skip", response_model=DailyTaskRead)
async def task_skip(
    resource_id: UUID,
    request: Request,
    body: TaskSkipRequest = Body(default_factory=TaskSkipRequest),
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.task_action(
        db, request.app.state.settings, actor.user_id, resource_id, key, "skip", body.reason
    )


@router.post("/review-tasks/{resource_id}/complete", response_model=ReviewCompleteResponse)
async def task_complete(
    resource_id: UUID,
    body: ReviewCompleteRequest,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    history = await complete_review(db, actor.user_id, resource_id, body, key)
    content = await learning.task_content(db, actor.user_id, resource_id)
    return {
        "task": content["task"],
        "schedule": content["schedule"],
        "history": ReviewHistoryRead.model_validate(history),
    }


@router.post("/review-tasks/{resource_id}/defer", response_model=DailyTaskRead)
async def task_defer(
    resource_id: UUID,
    body: TaskDeferRequest,
    request: Request,
    actor=Depends(current_user),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await learning.task_action(
        db, request.app.state.settings, actor.user_id, resource_id, key, "defer", days=body.days
    )


@router.get("/review-history", response_model=Page[ReviewHistoryRead])
async def histories(
    limit: int = Limit,
    cursor: str | None = None,
    knowledge_point_id: UUID | None = None,
    subject_id: UUID | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    rating: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    actor=Depends(current_user),
    db=Depends(database),
):
    return await learning.list_history(
        db, actor.user_id, limit, cursor, knowledge_point_id, subject_id, from_time, to_time, rating, q
    )


@router.get("/review-history/{resource_id}", response_model=ReviewHistoryRead)
async def history_get(resource_id: UUID, actor=Depends(current_user), db=Depends(database)):
    return await learning.get_resource(
        db, actor.user_id, ReviewHistory, resource_id, ReviewHistoryRead
    )


@router.get("/statistics/overview")
async def statistics(
    from_date: date,
    to_date: date,
    subject_id: UUID | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    return await learning.statistics(db, actor.user_id, from_date, to_date, subject_id)


@router.put("/knowledge-points/{resource_id}/schedule/strategy", response_model=ScheduleStateRead)
async def schedule_switch(
    resource_id: UUID,
    body: ScheduleSwitchRequest,
    actor=Depends(current_user),
    db=Depends(database),
    version=Depends(expected_version),
):
    return await learning.switch_schedule(db, actor.user_id, resource_id, body, version)

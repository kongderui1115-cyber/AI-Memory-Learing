"""Role-gated model governance and memory policy APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import administrator, database, expected_version, request_info
from app.contracts.admin_policies import (
    MemoryPolicyAdminRead,
    MemoryPolicyPage,
    MemoryPolicyPatch,
    MemorySimulationRead,
    MemorySimulationRequest,
    ModelProviderAdminPatch,
    ModelProviderAdminRead,
)
from app.contracts.models import Page
from app.services import admin_policies


router = APIRouter(tags=["administration"])
admin_dependency = Depends(administrator)
db_dependency = Depends(database)
version_dependency = Depends(expected_version)
page_limit = Query(default=20, ge=1, le=100)


@router.get("/admin/model-providers", response_model=Page[ModelProviderAdminRead])
async def model_providers(
    request: Request,
    user_id: UUID | None = None,
    limit: int = page_limit,
    cursor: str | None = None,
    actor=admin_dependency,
    db=db_dependency,
):
    return await admin_policies.model_providers(
        db, request.app.state.settings, actor, *request_info(request), user_id, limit, cursor
    )


@router.get("/admin/model-providers/{resource_id}/readiness", response_model=ModelProviderAdminRead)
async def model_readiness(resource_id: UUID, request: Request, actor=admin_dependency, db=db_dependency):
    return await admin_policies.read_model(
        db, request.app.state.settings, actor, *request_info(request), resource_id
    )


@router.patch("/admin/model-providers/{resource_id}", response_model=ModelProviderAdminRead)
async def model_update(
    resource_id: UUID,
    body: ModelProviderAdminPatch,
    request: Request,
    actor=admin_dependency,
    db=db_dependency,
    version=version_dependency,
):
    return await admin_policies.update_model(
        db, request.app.state.settings, actor, *request_info(request), resource_id, body, version
    )


@router.get("/admin/memory/policies", response_model=MemoryPolicyPage)
async def memory_policies(
    request: Request,
    user_id: UUID | None = None,
    limit: int = page_limit,
    cursor: str | None = None,
    actor=admin_dependency,
    db=db_dependency,
):
    return await admin_policies.memory_policies(
        db, request.app.state.settings, actor, *request_info(request), user_id, limit, cursor
    )


@router.patch("/admin/memory/policies/{resource_id}", response_model=MemoryPolicyAdminRead)
async def memory_update(
    resource_id: UUID,
    body: MemoryPolicyPatch,
    request: Request,
    actor=admin_dependency,
    db=db_dependency,
    version=version_dependency,
):
    return await admin_policies.update_memory_policy(
        db, request.app.state.settings, actor, *request_info(request), resource_id, body, version
    )


@router.post("/admin/memory/simulations", response_model=MemorySimulationRead)
async def memory_simulation(body: MemorySimulationRequest, request: Request, actor=admin_dependency):
    return admin_policies.simulate_memory(request.app.state.settings, body)

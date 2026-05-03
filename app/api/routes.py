"""
MIT License
API routes for provider validation, directory, audit logs, and statistics.
"""
import logging
import uuid
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.management_agent import run_management_agent
from app.api.schemas import (
    PaginatedProviders,
    ProviderResponse,
    StatsResponse,
    ValidationRequest,
    ValidationResponse,
    ProviderResultItem,
)
from app.auth.jwt_handler import get_current_user
from app.core.config import settings
from app.core.rate_limiter import limiter
from app.db.database import get_db
from app.db.models import AuditLog, Provider, ProviderStatus, ValidationResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["providers"])


async def _check_redis() -> bool:
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


async def _check_db(db: AsyncSession) -> bool:
    try:
        await db.execute(select(func.now()))
        return True
    except Exception:
        return False


@router.get("/health", include_in_schema=True)
async def health_check(db: AsyncSession = Depends(get_db)):
    db_ok = await _check_db(db)
    redis_ok = await _check_redis()
    return {
        "status": "healthy" if db_ok and redis_ok else "degraded",
        "version": "1.0.0",
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
    }


@router.post("/validate", response_model=ValidationResponse)
@limiter.limit("10/minute")
async def validate_providers(
    request: Request,
    payload: ValidationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    x_groq_key: str = Header(default=""),
):
    providers_data = [p.model_dump() for p in payload.providers]
    batch_result = await run_management_agent(providers_data, groq_key=x_groq_key)

    for item in batch_result["results"]:
        npi = item.get("npi")
        if not npi:
            continue
        existing = await db.execute(select(Provider).where(Provider.npi == npi))
        existing_provider = existing.scalar_one_or_none()

        if existing_provider is None:
            provider_input = next(
                (p for p in providers_data if p.get("npi") == npi), {}
            )
            final_status = item.get("final_status", "failed")
            status_map = {
                "approved": ProviderStatus.validated,
                "flagged": ProviderStatus.enriched,
                "failed": ProviderStatus.failed,
            }
            db_provider = Provider(
                id=uuid.uuid4(),
                npi=npi,
                name=provider_input.get("name", ""),
                specialty=provider_input.get("specialty"),
                phone=provider_input.get("phone"),
                address=provider_input.get("address"),
                city=provider_input.get("city"),
                state=provider_input.get("state"),
                zip_code=provider_input.get("zip_code"),
                status=status_map.get(final_status, ProviderStatus.failed),
            )
            db.add(db_provider)
            await db.flush()

            if item.get("validation_result"):
                vr = ValidationResult(
                    id=uuid.uuid4(),
                    provider_id=db_provider.id,
                    agent_name="validation_agent",
                    result=item["validation_result"],
                    confidence_score=item.get("confidence_score", 0.0),
                )
                db.add(vr)

            audit = AuditLog(
                id=uuid.uuid4(),
                provider_id=db_provider.id,
                action=f"batch_validation_{final_status}",
                details={
                    "confidence_score": item.get("confidence_score"),
                    "flags": item.get("qa_result", {}).get("flags") if item.get("qa_result") else [],
                },
            )
            db.add(audit)

    await db.commit()

    result_items = [
        ProviderResultItem(
            npi=r.get("npi"),
            name=r.get("name"),
            final_status=r.get("final_status", "failed"),
            confidence_score=r.get("confidence_score", 0.0),
            validation_result=r.get("validation_result"),
            enrichment_result=r.get("enrichment_result"),
            qa_result=r.get("qa_result"),
            error=r.get("error"),
        )
        for r in batch_result["results"]
    ]

    return ValidationResponse(
        batch_id=str(uuid.uuid4()),
        total=batch_result["total"],
        approved=batch_result["approved"],
        flagged=batch_result["flagged"],
        failed=batch_result["failed"],
        processing_time_seconds=batch_result["processing_time_seconds"],
        results=result_items,
    )


@router.get("/providers", response_model=PaginatedProviders)
@limiter.limit("60/minute")
async def list_providers(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    offset = (page - 1) * size
    query = select(Provider)
    count_query = select(func.count()).select_from(Provider)

    if status_filter:
        valid_statuses = [s.value for s in ProviderStatus]
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter. Must be one of: {valid_statuses}",
            )
        query = query.where(Provider.status == status_filter)
        count_query = count_query.where(Provider.status == status_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    result = await db.execute(query.offset(offset).limit(size))
    providers = result.scalars().all()

    return PaginatedProviders(
        total=total,
        page=page,
        size=size,
        items=[ProviderResponse.model_validate(p) for p in providers],
    )


@router.get("/providers/{provider_id}", response_model=ProviderResponse)
@limiter.limit("60/minute")
async def get_provider(
    request: Request,
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    return ProviderResponse.model_validate(provider)


@router.get("/audit/{provider_id}")
@limiter.limit("60/minute")
async def get_audit_log(
    request: Request,
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    provider_result = await db.execute(
        select(Provider).where(Provider.id == provider_id)
    )
    provider = provider_result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )

    logs_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.provider_id == provider_id)
        .order_by(AuditLog.performed_at.desc())
    )
    logs = logs_result.scalars().all()

    return {
        "provider_id": str(provider_id),
        "provider_npi": provider.npi,
        "audit_logs": [
            {
                "id": str(log.id),
                "action": log.action,
                "details": log.details,
                "performed_at": log.performed_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.get("/stats", response_model=StatsResponse)
@limiter.limit("60/minute")
async def get_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    total_result = await db.execute(select(func.count()).select_from(Provider))
    total = total_result.scalar() or 0

    status_result = await db.execute(
        select(Provider.status, func.count()).group_by(Provider.status)
    )
    providers_by_status = {row[0].value: row[1] for row in status_result.all()}

    specialty_result = await db.execute(
        select(Provider.specialty, func.count()).group_by(Provider.specialty)
    )
    providers_by_specialty = {
        (row[0] or "Unknown"): row[1] for row in specialty_result.all()
    }

    score_result = await db.execute(
        select(func.avg(ValidationResult.confidence_score))
    )
    avg_score = score_result.scalar() or 0.0

    validated_count = providers_by_status.get("validated", 0)
    approval_rate = round(validated_count / total, 2) if total > 0 else 0.0

    return StatsResponse(
        total_providers=total,
        approval_rate=approval_rate,
        average_confidence_score=round(float(avg_score), 2),
        providers_by_status=providers_by_status,
        providers_by_specialty=providers_by_specialty,
    )

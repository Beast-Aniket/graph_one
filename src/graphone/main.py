import asyncio
import csv
from datetime import UTC, datetime
from io import StringIO
import hashlib
import hmac
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.config import get_settings
from graphone.db import database_ok, get_session
from graphone.logging import configure_logging
from graphone.models import CrawlJob, IntelligenceRecord, Source
from graphone.schemas import CrawlRequest, GithubRefreshRequest, RecordInput, SourceCreate
from graphone.services.exports import csv_rows, send_google_sheets
from graphone.services.github import GithubMetricsError, refresh_github_metrics
from graphone.services.ingestion import RecordRejected, ingest_record
from graphone.worker import process_crawl_job
from graphone.worker import project_record

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    yield


app = FastAPI(title="GraphOne / FrontierAtlas API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not settings.api_key or not hmac.compare_digest(settings.api_key, x_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid X-API-Key is required.")


def source_view(source: Source) -> dict[str, object]:
    return {
        "id": source.id, "name": source.name, "base_url": source.base_url, "source_type": source.source_type,
        "parser_type": source.parser_type, "parser_config": source.parser_config, "enabled": source.enabled,
        "rate_limit_per_minute": source.rate_limit_per_minute, "last_crawled_at": source.last_crawled_at,
        "created_at": source.created_at,
    }


def job_view(job: CrawlJob) -> dict[str, object]:
    return {
        "id": job.id, "source_id": job.source_id, "status": job.status, "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts, "next_attempt_at": job.next_attempt_at, "last_error_code": job.last_error_code,
        "last_error_message": job.last_error_message, "result_summary": job.result_summary, "created_at": job.created_at,
        "completed_at": job.completed_at,
    }


def record_view(record: IntelligenceRecord) -> dict[str, object]:
    return {
        "id": record.id, "schemaVersion": record.schema_version, "recordType": record.record_type,
        "source": {"id": record.source_id, "name": record.source_name, "url": record.source_url},
        "canonical_url": record.canonical_url, "entity_name": record.entity_name,
        "canonical_entity_name": record.canonical_entity_name, "title": record.title,
        "published_at": record.published_at, "collected_at": record.collected_at,
        "freshness_status": record.freshness_status, "validation_status": record.validation_status,
        "processing_status": record.processing_status, "content": record.content, "provenance": record.provenance,
    }


@app.get(f"{settings.api_prefix}/health", tags=["operational"])
async def health() -> dict[str, object]:
    connected = await database_ok()
    return {"status": "ok" if connected else "degraded", "service": "graphone-frontieratlas", "database": "connected" if connected else "unavailable", "time_utc": datetime.now(UTC)}


@app.get(f"{settings.api_prefix}/sources", dependencies=[Depends(require_api_key)], tags=["sources"])
async def list_sources(enabled_only: bool = False, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    statement = select(Source).order_by(Source.source_type, Source.name)
    if enabled_only:
        statement = statement.where(Source.enabled.is_(True))
    return {"data": [source_view(source) for source in (await session.scalars(statement)).all()]}


@app.post(f"{settings.api_prefix}/sources", dependencies=[Depends(require_api_key)], status_code=201, tags=["sources"])
async def create_source(payload: SourceCreate, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    existing = await session.scalar(select(Source).where(Source.name == payload.name, Source.base_url == str(payload.base_url)))
    if existing:
        raise HTTPException(status_code=409, detail="A source with the same name and URL already exists.")
    source = Source(
        name=payload.name, base_url=str(payload.base_url), source_type=payload.source_type.value,
        parser_type=payload.parser_type, parser_config=payload.parser_config, enabled=payload.enabled,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return {"data": source_view(source)}


@app.post(f"{settings.api_prefix}/crawl-jobs", dependencies=[Depends(require_api_key)], status_code=202, tags=["crawling"])
async def queue_crawls(payload: CrawlRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    statement = select(Source).where(Source.enabled.is_(True))
    if payload.source_ids is not None:
        statement = statement.where(Source.id.in_(payload.source_ids))
    sources = (await session.scalars(statement)).all()
    if not sources:
        raise HTTPException(status_code=422, detail="No enabled authorized sources matched the request.")
    jobs: list[CrawlJob] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    for source in sources:
        base = payload.idempotency_prefix or str(uuid.uuid4())
        key = hashlib.sha256(f"{base}:{source.id}:{stamp}".encode()).hexdigest()
        job = CrawlJob(source_id=source.id, idempotency_key=key, max_attempts=settings.crawler_max_retries)
        session.add(job)
        jobs.append(job)
    await session.commit()
    for job in jobs:
        await session.refresh(job)
        process_crawl_job.delay(job.id)
    return {"data": [job_view(job) for job in jobs]}


@app.get(f"{settings.api_prefix}/crawl-jobs/{{job_id}}", dependencies=[Depends(require_api_key)], tags=["crawling"])
async def get_crawl_job(job_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    job = await session.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found.")
    return {"data": job_view(job)}


@app.post(f"{settings.api_prefix}/records", dependencies=[Depends(require_api_key)], status_code=201, tags=["records"])
async def create_record(payload: RecordInput, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        record, created = await ingest_record(session, payload)
    except RecordRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        project_record.delay(record.id)
    except Exception:
        logger.warning("graph_projection_not_queued", extra={"context": {"record_id": record.id}})
    return {"data": record_view(record), "created": created}


@app.get(f"{settings.api_prefix}/records", dependencies=[Depends(require_api_key)], tags=["records"])
async def list_records(
    record_type: str | None = None,
    source_id: str | None = None,
    fresh_only: bool = False,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    statement = select(IntelligenceRecord)
    if record_type:
        statement = statement.where(IntelligenceRecord.record_type == record_type.upper())
    if source_id:
        statement = statement.where(IntelligenceRecord.source_id == source_id)
    if fresh_only:
        statement = statement.where(IntelligenceRecord.freshness_status == "FRESH")
    if q:
        statement = statement.where(or_(IntelligenceRecord.title.ilike(f"%{q}%"), IntelligenceRecord.entity_name.ilike(f"%{q}%"), IntelligenceRecord.canonical_entity_name.ilike(f"%{q}%")))
    records = (await session.scalars(statement.order_by(IntelligenceRecord.published_at.desc().nullslast()).limit(limit).offset(offset))).all()
    return {"data": [record_view(record) for record in records]}


@app.get(f"{settings.api_prefix}/records/{{record_id}}", dependencies=[Depends(require_api_key)], tags=["records"])
async def get_record(record_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    record = await session.get(IntelligenceRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    return {"data": record_view(record)}


@app.post(f"{settings.api_prefix}/github/refresh", dependencies=[Depends(require_api_key)], tags=["enrichment"])
async def github_refresh(payload: GithubRefreshRequest, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        return {"data": await refresh_github_metrics(session, payload.record_id)}
    except GithubMetricsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(f"{settings.api_prefix}/exports/{{tab}}.csv", dependencies=[Depends(require_api_key)], tags=["exports"])
async def download_csv(tab: str, session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    try:
        headers, rows = await csv_rows(session, tab)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{tab}.csv"'})


@app.post(f"{settings.api_prefix}/exports/google-sheets", dependencies=[Depends(require_api_key)], tags=["exports"])
async def export_google_sheets(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        return {"data": await send_google_sheets(session)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import logging
import socket
from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select
from graphone.config import get_settings
from graphone.db import SessionLocal
from graphone.models import CrawlJob, Source
from graphone.services.crawling import CrawlFailure, CrawlProcessor
from graphone.services.graph import RelationshipGraph
from graphone.models import IntelligenceRecord

settings = get_settings()
logger = logging.getLogger(__name__)
celery_app = Celery("graphone", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={"schedule-enabled-sources": {"task": "graphone.schedule_enabled_sources", "schedule": crontab(minute="*/15")}},
)


async def _process(job_id: str) -> dict[str, object]:
    worker_id = f"{socket.gethostname()}:{id(asyncio.current_task())}"
    async with SessionLocal() as session:
        job = await session.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update(skip_locked=True))
        if not job:
            return {"status": "already_claimed"}
        if job.status not in {"PENDING", "RETRYING"}:
            return {"status": job.status.lower()}
        source = await session.get(Source, job.source_id)
        if not source or not source.enabled:
            job.status = "NEEDS_REVIEW"
            job.last_error_message = "Source is unavailable or disabled."
            await session.commit()
            return {"status": "needs_review"}
        job.status = "PROCESSING"
        job.locked_by = worker_id
        job.locked_at = datetime.now(UTC)
        job.started_at = job.started_at or datetime.now(UTC)
        job.attempt_count += 1
        await session.commit()
        try:
            summary = await CrawlProcessor().process(session, job, source)
            job.status = "COMPLETED"
            job.completed_at = datetime.now(UTC)
            job.locked_at = None
            job.locked_by = None
            job.result_summary = summary
            job.last_error_code = None
            job.last_error_message = None
            await session.commit()
            return {"status": "completed", "summary": summary}
        except CrawlFailure as exc:
            job.locked_at = None
            job.locked_by = None
            job.last_error_code = exc.code
            job.last_error_message = str(exc)
            if exc.needs_review:
                job.status = "NEEDS_REVIEW"
                await session.commit()
                return {"status": "needs_review"}
            if job.attempt_count >= job.max_attempts:
                job.status = "FAILED"
                await session.commit()
                return {"status": "failed", "reason": str(exc)}
            delay = exc.retry_after or min(3600, 2 ** min(job.attempt_count, 10) + (hash(job.id) % 15))
            job.status = "RETRYING"
            job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            await session.commit()
            return {"status": "retry", "delay": delay, "reason": str(exc)}
        except Exception as exc:
            logger.exception("crawl_job_error", extra={"context": {"job_id": job_id}})
            job.locked_at = None
            job.locked_by = None
            job.last_error_code = "WORKER_ERROR"
            job.last_error_message = str(exc)[:2000]
            if job.attempt_count >= job.max_attempts:
                job.status = "FAILED"
                await session.commit()
                return {"status": "failed", "reason": str(exc)}
            delay = min(3600, 2 ** min(job.attempt_count, 10) + (hash(job.id) % 15))
            job.status = "RETRYING"
            job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            await session.commit()
            return {"status": "retry", "delay": delay, "reason": str(exc)}


@celery_app.task(name="graphone.process_crawl_job", bind=True, max_retries=None)
def process_crawl_job(self, job_id: str) -> dict[str, object]:
    result = asyncio.run(_process(job_id))
    if result.get("status") == "retry":
        raise self.retry(countdown=int(result["delay"]))
    return result


async def _schedule_enabled_sources() -> int:
    async with SessionLocal() as session:
        sources = (await session.scalars(select(Source).where(Source.enabled.is_(True)))).all()
        count = 0
        for source in sources:
            key = hashlib.sha256(f"scheduled:{source.id}:{datetime.now(UTC):%Y%m%d%H%M}".encode()).hexdigest()
            existing = await session.scalar(select(CrawlJob).where(CrawlJob.idempotency_key == key))
            if not existing:
                job = CrawlJob(source_id=source.id, idempotency_key=key, max_attempts=settings.crawler_max_retries)
                session.add(job)
                await session.flush()
                process_crawl_job.delay(job.id)
                count += 1
        await session.commit()
        return count


@celery_app.task(name="graphone.schedule_enabled_sources")
def schedule_enabled_sources() -> int:
    return asyncio.run(_schedule_enabled_sources())


async def _project_record(record_id: str) -> None:
    async with SessionLocal() as session:
        record = await session.get(IntelligenceRecord, record_id)
        if record:
            await RelationshipGraph().upsert_record(record.id, record.record_type, record.canonical_entity_name, record.title)


@celery_app.task(name="graphone.project_record", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def project_record(record_id: str) -> None:
    """Retryable secondary Neo4j projection; a graph outage never loses PostgreSQL source-of-truth data."""
    asyncio.run(_project_record(record_id))


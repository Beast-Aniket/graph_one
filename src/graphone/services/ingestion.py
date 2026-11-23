from datetime import UTC, datetime
import hashlib
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.models import EntityMapping, IntelligenceRecord
from graphone.schemas import JobContent, NewsContent, ProductContent, RecordInput, RecordType, ResearchPaperContent, StartupContent, parse_content
from graphone.services.entities import Resolution, resolve_entity
from graphone.services.freshness import assess_freshness


class RecordRejected(ValueError):
    pass


def _json(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=False)


def _entity(record_type: RecordType, content: Any) -> str | None:
    if isinstance(content, StartupContent):
        return content.entity_name
    if isinstance(content, ProductContent):
        return content.startup_name
    if isinstance(content, JobContent):
        return content.company
    return None


def _title(content: Any) -> str | None:
    if isinstance(content, (NewsContent, ResearchPaperContent)):
        return content.title
    if isinstance(content, ProductContent):
        return content.name
    return None


def _published_at(content: Any) -> datetime | None:
    if isinstance(content, (NewsContent, ResearchPaperContent)):
        return content.published_date
    if isinstance(content, JobContent):
        return content.date
    return None


def _canonical_url(content: Any, source_url: str) -> str:
    if isinstance(content, (NewsContent, JobContent)) and content.canonical_url:
        return str(content.canonical_url)
    if isinstance(content, ResearchPaperContent):
        return str(content.paper_url)
    return source_url


def _dedupe_key(record_type: RecordType, content: Any, canonical_url: str, resolution: Resolution | None) -> str:
    identity: str
    if record_type == RecordType.STARTUP:
        identity = resolution.canonical_key if resolution else str(content.entity_name)
    elif record_type == RecordType.PRODUCT:
        identity = canonical_url
    elif record_type == RecordType.RESEARCH_PAPER:
        identity = str(content.paper_url)
    elif record_type == RecordType.NEWS:
        identity = str(content.canonical_url)
    else:
        identity = f"{canonical_url}|{content.date.isoformat() if content.date else 'unverified'}"
    return hashlib.sha256(f"{record_type}|{identity.strip().lower()}".encode()).hexdigest()


async def ingest_record(session: AsyncSession, payload: RecordInput, *, reject_stale: bool = True) -> tuple[IntelligenceRecord, bool]:
    content = parse_content(payload.record_type, payload.content)
    published_at = _published_at(content)
    freshness_status, needs_review = assess_freshness(payload.record_type, published_at)
    if reject_stale and freshness_status == "STALE":
        raise RecordRejected("News and jobs older than 24 hours cannot be accepted as current intelligence.")
    entity_name = _entity(payload.record_type, content)
    resolution = await resolve_entity(session, entity_name) if entity_name else None
    canonical_url = _canonical_url(content, str(payload.source.url))
    dedupe_key = _dedupe_key(payload.record_type, content, canonical_url, resolution)
    now = datetime.now(UTC)
    content_json = _json(content)
    content_hash = hashlib.sha256(json.dumps(content_json, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = await session.scalar(select(IntelligenceRecord).where(IntelligenceRecord.dedupe_key == dedupe_key).with_for_update())
    validation_status = "NEEDS_REVIEW" if needs_review or (resolution and resolution.needs_review) else "VALID"
    processing_status = "NEEDS_REVIEW" if validation_status == "NEEDS_REVIEW" else "COMPLETED"
    values = dict(
        schema_version=payload.schema_version,
        record_type=payload.record_type.value,
        source_id=payload.source.id,
        raw_document_id=payload.raw_document_id,
        source_name=payload.source.name,
        source_url=str(payload.source.url),
        canonical_url=canonical_url,
        entity_name=entity_name,
        canonical_entity_name=resolution.canonical_name if resolution else None,
        title=_title(content),
        published_at=published_at,
        last_seen_at=now,
        last_processed_at=now,
        freshness_status=freshness_status,
        validation_status=validation_status,
        processing_status=processing_status,
        content=content_json,
        provenance={
            "source_name": payload.source.name,
            "source_url": str(payload.source.url),
            "raw_document_id": payload.raw_document_id,
            "extraction_provider": payload.extraction_provider,
            "collected_at": (payload.collected_at or now).isoformat(),
        },
        content_hash=content_hash,
    )
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        record, created = existing, False
    else:
        record = IntelligenceRecord(dedupe_key=dedupe_key, collected_at=payload.collected_at or now, **values)
        session.add(record)
        await session.flush()
        created = True
    if resolution:
        session.add(EntityMapping(
            raw_name=resolution.raw_name,
            normalized_name=resolution.normalized_name,
            canonical_name=resolution.canonical_name,
            canonical_key=resolution.canonical_key,
            confidence=resolution.confidence,
            resolution_method=resolution.method,
            needs_review=resolution.needs_review,
            source_record_id=record.id,
        ))
    await session.commit()
    await session.refresh(record)
    return record, created


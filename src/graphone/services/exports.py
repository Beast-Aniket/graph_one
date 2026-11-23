from collections.abc import Sequence
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.config import get_settings
from graphone.models import EntityMapping, IntelligenceRecord

TABS = {
    "startups": "STARTUP", "products": "PRODUCT", "research-papers": "RESEARCH_PAPER", "jobs": "JOB", "news": "NEWS"
}


async def csv_rows(session: AsyncSession, tab: str) -> tuple[list[str], list[list[Any]]]:
    if tab == "entity-mapping":
        mappings = (await session.scalars(select(EntityMapping).order_by(EntityMapping.created_at.desc()))).all()
        return ["raw_name", "canonical_name", "confidence", "resolution_method", "needs_review", "mapped_at"], [
            [item.raw_name, item.canonical_name, item.confidence, item.resolution_method, item.needs_review, item.created_at.isoformat()] for item in mappings
        ]
    if tab not in TABS:
        raise ValueError("Unknown export tab.")
    records = (await session.scalars(select(IntelligenceRecord).where(IntelligenceRecord.record_type == TABS[tab]).order_by(IntelligenceRecord.published_at.desc().nullslast()))).all()
    headers = ["id", "record_type", "source_name", "source_url", "canonical_url", "entity_name", "canonical_entity_name", "title", "published_at", "collected_at", "freshness_status", "validation_status", "content_json"]
    rows = [[record.id, record.record_type, record.source_name, record.source_url, record.canonical_url, record.entity_name, record.canonical_entity_name, record.title, record.published_at.isoformat() if record.published_at else "", record.collected_at.isoformat(), record.freshness_status, record.validation_status, __import__("json").dumps(record.content)] for record in records]
    return headers, rows


async def send_google_sheets(session: AsyncSession) -> dict[str, object]:
    settings = get_settings()
    if not settings.google_sheets_webhook_url:
        raise ValueError("GOOGLE_SHEETS_WEBHOOK_URL is not configured.")
    display = {"startups": "Startups", "products": "Products", "research-papers": "Research Papers", "jobs": "Jobs", "news": "News", "entity-mapping": "Entity Mapping Log"}
    payload = {"tabs": {display[tab]: {"headers": headers, "rows": rows} for tab in [*TABS, "entity-mapping"] for headers, rows in [await csv_rows(session, tab)]}}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(settings.google_sheets_webhook_url, json=payload)
    response.raise_for_status()
    return {"sent_tabs": list(payload["tabs"]), "status": response.status_code}


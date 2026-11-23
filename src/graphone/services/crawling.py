from datetime import UTC, datetime
import hashlib
import logging
from typing import Any
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.config import get_settings
from graphone.models import CrawlJob, RawDocument, Source
from graphone.schemas import RecordInput
from graphone.services.ingestion import RecordRejected, ingest_record
from graphone.services.llm import LlmOrchestrator
from graphone.services.storage import ObjectStorage

logger = logging.getLogger(__name__)


class CrawlFailure(RuntimeError):
    def __init__(self, message: str, code: str, retry_after: int | None = None, needs_review: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after
        self.needs_review = needs_review


def clean_html(content: str) -> str:
    soup = BeautifulSoup(content, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _published(item: Any) -> str | None:
    for tag in ("pubDate", "published", "updated"):
        node = item.find(tag)
        if node and node.text:
            try:
                from email.utils import parsedate_to_datetime

                value = parsedate_to_datetime(node.text) if tag == "pubDate" else datetime.fromisoformat(node.text.replace("Z", "+00:00"))
                return value.astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                return None
    return None


def parse_rss(content: str, base_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(content, "xml")
    entries = soup.find_all("item") or soup.find_all("entry")
    results: list[dict[str, str | None]] = []
    for entry in entries:
        link_tag = entry.find("link")
        link = (link_tag.get("href") if link_tag else None) or (link_tag.text if link_tag else "")
        if not link:
            continue
        title = entry.find("title")
        description = entry.find("description") or entry.find("summary") or entry.find("content")
        results.append({
            "url": urljoin(base_url, link.strip()),
            "title": title.get_text(" ", strip=True) if title else "",
            "description": description.get_text(" ", strip=True) if description else "",
            "published_at": _published(entry),
        })
    return results


class CrawlProcessor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage = ObjectStorage()

    async def process(self, session: AsyncSession, job: CrawlJob, source: Source) -> dict[str, int]:
        headers = {"User-Agent": self.settings.crawler_user_agent, "Accept": "application/rss+xml, application/xml, text/xml, application/json, text/html;q=0.9, */*;q=0.8"}
        async with httpx.AsyncClient(headers=headers, timeout=self.settings.crawler_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(source.base_url)
            self._validate_response(response)
            root = await self._save_raw(session, job, source, response, clean_html(response.text))
            summary = {"fetched": 1, "created": 0, "updated": 0, "review": 0, "skipped": 0}
            if source.parser_type == "RSS":
                items = parse_rss(response.text, source.base_url)
                # Each worker is asynchronous and Celery runs several workers concurrently. Process the
                # source's database writes in order on this session to preserve transaction integrity.
                for item in items:
                    outcome = await self._process_rss_item(session, client, job, source, item, root.id)
                    for key, value in outcome.items():
                        summary[key] += value
            else:
                outcome = await self._process_text(session, source, clean_html(response.text), response.url, root.id, None, None, None)
                for key, value in outcome.items():
                    summary[key] += value
            source.last_crawled_at = datetime.now(UTC)
            await session.commit()
            return summary

    async def _process_rss_item(self, session: AsyncSession, client: httpx.AsyncClient, job: CrawlJob, source: Source, item: dict[str, str | None], root_id: str) -> dict[str, int]:
        raw_id = root_id
        detail_text = item["description"] or ""
        if source.source_type == "NEWS":
            try:
                detail = await client.get(str(item["url"]))
                self._validate_response(detail)
                detail_text = clean_html(detail.text)
                raw = await self._save_raw(session, job, source, detail, detail_text)
                raw_id = raw.id
            except CrawlFailure:
                return {"fetched": 0, "created": 0, "updated": 0, "review": 1, "skipped": 0}
        return await self._process_text(session, source, f"{item['title'] or ''}\n{detail_text}", str(item["url"]), raw_id, item["title"], item["published_at"], detail_text)

    async def _process_text(self, session: AsyncSession, source: Source, text: str, url: str, raw_document_id: str, title: str | None, published_at: str | None, full_text: str | None) -> dict[str, int]:
        payload: dict[str, Any] | None = None
        provider = "RSS_DETERMINISTIC"
        if source.source_type == "NEWS" and title and full_text:
            payload = {"title": title, "full_text": full_text, "published_date": published_at, "canonical_url": url}
        else:
            llm = LlmOrchestrator()
            try:
                payload, provider_name = await llm.extract(source.source_type, text)
                provider = provider_name or "UNAVAILABLE"
            finally:
                await llm.close()
        if payload is None:
            return {"fetched": 0, "created": 0, "updated": 0, "review": 1, "skipped": 0}
        try:
            input_data = RecordInput.model_validate({
                "recordType": source.source_type,
                "source": {"id": source.id, "name": source.name, "url": url},
                "content": payload,
                "rawDocumentId": raw_document_id,
                "extractionProvider": provider,
            })
            record, created = await ingest_record(session, input_data)
            try:
                from graphone.worker import project_record
                project_record.delay(record.id)
            except Exception:
                logger.warning("graph_projection_not_queued", extra={"context": {"record_id": record.id}})
            return {"fetched": 0, "created": int(created), "updated": int(not created), "review": 0, "skipped": 0}
        except RecordRejected:
            return {"fetched": 0, "created": 0, "updated": 0, "review": 0, "skipped": 1}
        except Exception:
            logger.exception("item_validation_failed", extra={"context": {"source_id": source.id, "url": url}})
            return {"fetched": 0, "created": 0, "updated": 0, "review": 1, "skipped": 0}

    async def _save_raw(self, session: AsyncSession, job: CrawlJob, source: Source, response: httpx.Response, text: str) -> RawDocument:
        await self.storage.ensure_bucket()
        object_key, digest = await self.storage.put_raw(source.id, response.content, response.headers.get("content-type"))
        document = RawDocument(
            crawl_job_id=job.id,
            source_id=source.id,
            source_url=str(response.request.url),
            final_url=str(response.url),
            http_status=response.status_code,
            content_type=response.headers.get("content-type"),
            content_sha256=digest,
            object_key=object_key,
            extracted_text=text,
            response_headers=dict(response.headers),
        )
        session.add(document)
        await session.flush()
        return document

    @staticmethod
    def _validate_response(response: httpx.Response) -> None:
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise CrawlFailure("Source rate limited the request.", "HTTP_429", int(retry_after) if retry_after and retry_after.isdigit() else None)
        if response.status_code == 413:
            raise CrawlFailure("Source returned payload-too-large response.", "HTTP_413")
        if response.status_code in {401, 403} or "captcha" in response.text.lower():
            raise CrawlFailure("Source is blocked or requires manual authorization.", "SOURCE_BLOCKED", needs_review=True)
        if response.is_error:
            raise CrawlFailure(f"Source returned HTTP {response.status_code}.", f"HTTP_{response.status_code}")


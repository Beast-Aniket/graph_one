from datetime import UTC, datetime, timedelta
import pytest
import httpx
from pydantic import ValidationError
from graphone.schemas import RecordInput, RecordType, parse_content
from graphone.services.chunking import semantic_chunks
from graphone.services.crawling import parse_rss
from graphone.services.entities import normalize_name
from graphone.services.freshness import assess_freshness
from graphone.services.llm import ExtractionError, LlmOrchestrator


def test_normalizer_maps_company_suffixes_without_overmerging() -> None:
    assert normalize_name(" OpenAI, Inc. ") == "openai"
    assert normalize_name("Google DeepMind") == "google deepmind"


def test_freshness_enforces_exact_prd_twenty_four_hour_boundary() -> None:
    now = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
    assert assess_freshness(RecordType.NEWS, now - timedelta(hours=23, minutes=59), now) == ("FRESH", False)
    assert assess_freshness(RecordType.JOB, now - timedelta(hours=24, minutes=1), now) == ("STALE", False)
    assert assess_freshness(RecordType.NEWS, None, now) == ("UNVERIFIED", True)
    assert assess_freshness(RecordType.RESEARCH_PAPER, None, now) == ("NOT_APPLICABLE", False)


def test_semantic_chunks_keep_size_limit() -> None:
    chunks = semantic_chunks("One sentence. Two sentence. Three sentence.", 20)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 20 for chunk in chunks)


def test_rss_parser_normalizes_absolute_links_and_publication_time() -> None:
    feed = """<rss><channel><item><title>AI launch</title><link>/story</link><description>Summary</description><pubDate>Mon, 23 Nov 2026 08:00:00 +0000</pubDate></item></channel></rss>"""
    items = parse_rss(feed, "https://news.example/feed.xml")
    assert items == [{"url": "https://news.example/story", "title": "AI launch", "description": "Summary", "published_at": "2026-11-23T08:00:00+00:00"}]


def test_record_schema_preserves_prd_field_shape() -> None:
    record = RecordInput.model_validate({
        "recordType": "STARTUP",
        "source": {"name": "Directory", "url": "https://directory.example/openai"},
        "content": {"entityName": "OpenAI", "data": {"employeeCount": 1200}},
    })
    content = parse_content(record.record_type, record.content)
    assert content.model_dump(by_alias=True)["entityName"] == "OpenAI"
    assert content.model_dump(by_alias=True)["data"]["employeeCount"] == 1200


def test_invalid_pricing_model_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_content(RecordType.PRODUCT, {"startupName": "OpenAI", "pricingModel": "MAYBE"})


def test_unknown_news_date_is_kept_for_review_instead_of_fabricated() -> None:
    content = parse_content(RecordType.NEWS, {"title": "Undated", "full_text": "Source text", "published_date": None, "canonical_url": "https://news.example/story"})
    assert content.published_date is None


@pytest.mark.parametrize("status_code", [413, 429])
def test_llm_provider_special_failures_are_explicit(status_code: int) -> None:
    with pytest.raises(ExtractionError) as error:
        LlmOrchestrator._raise_for_provider_response(httpx.Response(status_code))
    assert error.value.status_code == status_code


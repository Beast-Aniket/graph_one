import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector(1536)"


class Base(DeclarativeBase):
    pass


def uuid_str() -> str:
    return str(uuid.uuid4())


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_type: Mapped[str] = mapped_column(Enum("STARTUP", "PRODUCT", "RESEARCH_PAPER", "JOB", "NEWS", name="source_type"), nullable=False)
    parser_type: Mapped[str] = mapped_column(Enum("RSS", "HTML", "JSON", "LLM", name="parser_type"), nullable=False, default="RSS")
    parser_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("name", "base_url", name="uq_source_name_url"), Index("ix_sources_enabled_type", "enabled", "source_type"))


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRYING", "NEEDS_REVIEW", name="processing_status"), nullable=False, default="PENDING")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(String(2000))
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (Index("ix_crawl_jobs_claim", "status", "next_attempt_at", "priority"),)


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    crawl_job_id: Mapped[str] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    response_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IntelligenceRecord(Base):
    __tablename__ = "intelligence_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    record_type: Mapped[str] = mapped_column(Enum("STARTUP", "PRODUCT", "RESEARCH_PAPER", "JOB", "NEWS", name="record_type"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    raw_document_id: Mapped[str | None] = mapped_column(ForeignKey("raw_documents.id", ondelete="SET NULL"))
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    entity_name: Mapped[str | None] = mapped_column(String(512))
    canonical_entity_name: Mapped[str | None] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(1024))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_status: Mapped[str] = mapped_column(Enum("NOT_APPLICABLE", "FRESH", "STALE", "UNVERIFIED", name="freshness_status"), nullable=False, default="NOT_APPLICABLE")
    validation_status: Mapped[str] = mapped_column(Enum("VALID", "INVALID", "NEEDS_REVIEW", name="validation_status"), nullable=False)
    processing_status: Mapped[str] = mapped_column(Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRYING", "NEEDS_REVIEW", name="record_processing_status"), nullable=False, default="COMPLETED")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[Any | None] = mapped_column(Vector(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    __table_args__ = (
        Index("ix_records_type_published", "record_type", "published_at"),
        Index("ix_records_source_collected", "source_id", "collected_at"),
        Index("ix_records_freshness", "record_type", "freshness_status", "published_at"),
        Index("ix_records_entity", "canonical_entity_name"),
    )


class CanonicalEntity(Base):
    __tablename__ = "canonical_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_seed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EntityMapping(Base):
    __tablename__ = "entity_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    raw_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_method: Mapped[str] = mapped_column(Enum("EXACT", "SEED_ALIAS", "CONSERVATIVE_MATCH", "MANUAL", name="resolution_method"), nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("intelligence_records.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RepositoryMetric(Base):
    __tablename__ = "repository_metrics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("intelligence_records.id", ondelete="SET NULL"))
    repository_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    repository_full_name: Mapped[str | None] = mapped_column(String(512))
    stars_count: Mapped[int | None] = mapped_column(Integer)
    forks_count: Mapped[int | None] = mapped_column(Integer)
    open_issues_count: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


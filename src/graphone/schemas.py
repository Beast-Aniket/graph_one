from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


class RecordType(StrEnum):
    STARTUP = "STARTUP"
    PRODUCT = "PRODUCT"
    RESEARCH_PAPER = "RESEARCH_PAPER"
    JOB = "JOB"
    NEWS = "NEWS"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SourceRef(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    url: AnyHttpUrl


class EmployeeData(BaseModel):
    employee_count: int | None = Field(default=None, ge=0, validation_alias="employeeCount", serialization_alias="employeeCount")


class StartupContent(BaseModel):
    entity_name: str = Field(min_length=1, validation_alias="entityName", serialization_alias="entityName")
    data: EmployeeData = Field(default_factory=EmployeeData)


class ProductContent(BaseModel):
    startup_name: str = Field(min_length=1, validation_alias="startupName", serialization_alias="startupName")
    pricing_model: Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"] = Field(validation_alias="pricingModel", serialization_alias="pricingModel")
    name: str | None = None


class ResearchPaperContent(BaseModel):
    title: str = Field(min_length=1)
    authors: list[str] = Field(min_length=1)
    paper_url: AnyHttpUrl
    github_url: AnyHttpUrl | None = None
    github_stars: int | None = Field(default=None, ge=0)
    published_date: datetime


class JobContent(BaseModel):
    company: str = Field(min_length=1)
    date: datetime | None = None
    is_remote: bool
    role_family: str = Field(min_length=1)
    canonical_url: AnyHttpUrl | None = None


class NewsContent(BaseModel):
    title: str = Field(min_length=1)
    full_text: str = Field(min_length=1)
    published_date: datetime | None = None
    canonical_url: AnyHttpUrl


CanonicalContent = StartupContent | ProductContent | ResearchPaperContent | JobContent | NewsContent


class RecordInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="1.0", validation_alias="schemaVersion", serialization_alias="schemaVersion")
    record_type: RecordType = Field(validation_alias="recordType", serialization_alias="recordType")
    source: SourceRef
    content: dict[str, Any]
    collected_at: datetime | None = Field(default=None, validation_alias="collectedAt", serialization_alias="collectedAt")
    raw_document_id: str | None = Field(default=None, validation_alias="rawDocumentId", serialization_alias="rawDocumentId")
    extraction_provider: str = Field(default="DIRECT_API", validation_alias="extractionProvider", serialization_alias="extractionProvider")

    @field_validator("collected_at")
    @classmethod
    def collected_at_utc(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value else value


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    base_url: AnyHttpUrl
    source_type: RecordType
    parser_type: Literal["RSS", "HTML", "JSON", "LLM"] = "RSS"
    parser_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)


class CrawlRequest(BaseModel):
    source_ids: list[str] | None = None
    idempotency_prefix: str | None = Field(default=None, max_length=200)


class GithubRefreshRequest(BaseModel):
    record_id: str


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must include a timezone.")
    return value.astimezone(UTC)


def parse_content(record_type: RecordType, content: dict[str, Any]) -> CanonicalContent:
    model: type[CanonicalContent]
    match record_type:
        case RecordType.STARTUP:
            model = StartupContent
        case RecordType.PRODUCT:
            model = ProductContent
        case RecordType.RESEARCH_PAPER:
            model = ResearchPaperContent
        case RecordType.JOB:
            model = JobContent
        case RecordType.NEWS:
            model = NewsContent
    parsed = model.model_validate(content)
    if hasattr(parsed, "published_date") and parsed.published_date is not None:  # type: ignore[attr-defined]
        parsed.published_date = ensure_utc(parsed.published_date)  # type: ignore[attr-defined]
    if hasattr(parsed, "date") and parsed.date is not None:  # type: ignore[attr-defined]
        parsed.date = ensure_utc(parsed.date)  # type: ignore[attr-defined]
    return parsed


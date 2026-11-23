from datetime import UTC, datetime, timedelta
from graphone.schemas import RecordType


def assess_freshness(record_type: RecordType, published_at: datetime | None, now: datetime | None = None) -> tuple[str, bool]:
    """Return (status, needs_review) using the PRD's published_at >= now - 24h rule."""
    if record_type not in {RecordType.NEWS, RecordType.JOB}:
        return "NOT_APPLICABLE", False
    if published_at is None:
        return "UNVERIFIED", True
    now = now or datetime.now(UTC)
    if published_at > now + timedelta(minutes=5):
        return "UNVERIFIED", True
    if published_at < now - timedelta(hours=24):
        return "STALE", False
    return "FRESH", False


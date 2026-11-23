from datetime import UTC, datetime
import re
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from graphone.config import get_settings
from graphone.models import IntelligenceRecord, RepositoryMetric

GITHUB_URL = re.compile(r"^https://github\.com/([^/]+)/([^/?#]+)", re.I)


class GithubMetricsError(ValueError):
    pass


async def refresh_github_metrics(session: AsyncSession, record_id: str) -> dict[str, object]:
    record = await session.get(IntelligenceRecord, record_id)
    if not record or record.record_type != "RESEARCH_PAPER":
        raise GithubMetricsError("Research paper record not found.")
    url = record.content.get("github_url")
    match = GITHUB_URL.match(url or "")
    if not match:
        raise GithubMetricsError("Research paper has no valid GitHub repository URL.")
    settings = get_settings()
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    async with httpx.AsyncClient(timeout=settings.crawler_timeout_seconds, headers=headers) as client:
        response = await client.get(f"https://api.github.com/repos/{match.group(1)}/{match.group(2)}")
    if response.status_code in {403, 429}:
        raise GithubMetricsError("GitHub API rate limit reached; retry later.")
    if response.is_error:
        raise GithubMetricsError(f"GitHub API returned HTTP {response.status_code}.")
    data = response.json()
    metrics = {
        "repository": f"{match.group(1)}/{match.group(2)}",
        "stars": int(data.get("stargazers_count", 0)),
        "forks": int(data.get("forks_count", 0)),
        "open_issues": int(data.get("open_issues_count", 0)),
        "observed_at": datetime.now(UTC).isoformat(),
    }
    session.add(RepositoryMetric(
        record_id=record.id,
        repository_url=url,
        repository_full_name=metrics["repository"],
        stars_count=metrics["stars"],
        forks_count=metrics["forks"],
        open_issues_count=metrics["open_issues"],
        observed_at=datetime.now(UTC),
        response_status=response.status_code,
    ))
    record.content = {**record.content, "github_stars": metrics["stars"]}
    await session.commit()
    return metrics


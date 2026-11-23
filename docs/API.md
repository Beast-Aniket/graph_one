# GraphOne API

Base URL: `http://localhost:8000/api/v1`. Every endpoint except `GET /health` requires `X-API-Key` equal to `API_KEY` in `.env`.

| Method | Path | Use |
| --- | --- | --- |
| GET | `/health` | Service/database health |
| GET, POST | `/sources` | List or configure permitted sources |
| POST | `/crawl-jobs` | Queue all enabled or selected sources |
| GET | `/crawl-jobs/{id}` | Inspect a crawl job and retries |
| GET, POST | `/records` | Search or directly ingest validated intelligence |
| GET | `/records/{id}` | Get a record and provenance |
| POST | `/github/refresh` | Refresh paper repository metrics |
| GET | `/exports/{tab}.csv` | Export one required tab |
| POST | `/exports/google-sheets` | Deliver all six tabs through Apps Script webhook |

## Sources

```json
{
  "name": "Approved AI news RSS",
  "base_url": "https://publisher.example/ai.xml",
  "source_type": "NEWS",
  "parser_type": "RSS",
  "parser_config": {"notes": "Authorized source"},
  "enabled": true,
  "rate_limit_per_minute": 10
}
```

Only enable a source after confirming permission, terms, robots policy, and an appropriate rate limit.

## Direct records

The API keeps original source identity/URL, validates the canonical record schema, and calculates a deterministic dedupe key. News/jobs must be within the prior 24 hours; items without a trustworthy time are `UNVERIFIED`, not fresh.

```json
{
  "schemaVersion": "1.0",
  "recordType": "RESEARCH_PAPER",
  "source": {"name": "arXiv", "url": "https://arxiv.org/abs/1234.5678"},
  "content": {
    "title": "Example research",
    "authors": ["A. Researcher"],
    "paper_url": "https://arxiv.org/abs/1234.5678",
    "github_url": "https://github.com/org/repository",
    "github_stars": null,
    "published_date": "2026-11-23T08:00:00Z"
  }
}
```

## Exports and Google Sheets

Valid CSV tabs are `startups`, `products`, `research-papers`, `jobs`, `news`, and `entity-mapping`. Configure a protected Apps Script endpoint in `GOOGLE_SHEETS_WEBHOOK_URL`; the endpoint receives:

```json
{"tabs":{"Startups":{"headers":["..."],"rows":[["..."]]}}}
```

Deploy [integrations/google_apps_script.js](../integrations/google_apps_script.js) as a protected Apps Script web app. It clears/writes the six required tabs: Startups, Products, Research Papers, Jobs, News, and Entity Mapping Log.


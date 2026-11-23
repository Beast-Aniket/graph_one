# PRD-aligned architecture

```text
Authorized source configuration
  -> Celery scheduler / Redis queue
  -> asynchronous httpx crawling workers
  -> MinIO raw HTML/text evidence
  -> cleaning + freshness gate
  -> Gemini -> Groq -> DeepSeek grounded JSON extraction
  -> Pydantic validation + entity resolution + atomic dedupe
  -> PostgreSQL + pgvector (system of record)
  -> Neo4j relationship projection
  -> FastAPI, CSV, Google Sheets export
```

## Reliability and quality

- Jobs persist `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `RETRYING`, and `NEEDS_REVIEW` status in PostgreSQL.
- Celery tasks use late acknowledgement; row locks guard claiming; deterministic idempotency keys and unique dedupe keys prevent repeat work.
- HTTP 429 uses an exponential retry policy; HTTP 413 uses semantic LLM chunking; block/CAPTCHA/401/403 cases go to review rather than being bypassed.
- All time comparisons are UTC. News and jobs are `FRESH` only within 24 hours of publication; unavailable dates are not treated as fresh.
- Every structured record holds raw-document linkage, original source URL/name, provider, collection time, normalized timestamps, and validation state.
- PostgreSQL is authoritative. Neo4j is a retryable projection, so a graph outage cannot discard collected intelligence.

## Scale path

Independent containers make API, workers, and scheduler horizontally scalable. PostgreSQL indexes the queue claim path, types/dates, entities, and freshness. At higher volumes, scale workers independently, use managed object storage, partition historical tables, and put pgvector/Neo4j behind the existing durable record IDs.


# GraphOne / FrontierAtlas

PRD-aligned backend for global AI intelligence collection, extraction, enrichment, entity resolution, graph relationships, and exports.

Technology follows the PRD: **Python, FastAPI, httpx, Celery + Redis, PostgreSQL + pgvector, MinIO-compatible object storage, Neo4j, Pydantic, Docker, and structured JSON logs.** No WAMP, PHP, Apache, or MySQL component is used.

The complete local setup and run instructions are in [SETUP_AND_RUN.txt](SETUP_AND_RUN.txt). The API contract is in [docs/API.md](docs/API.md), and the architecture is in [architecture.pdf](architecture.pdf).

Safety boundary: only configure sources you are authorized to collect. The worker respects 401/403/CAPTCHA blocks by moving jobs to review; it does not bypass access controls.


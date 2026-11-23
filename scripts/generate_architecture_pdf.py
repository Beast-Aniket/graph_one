"""Generate the PRD-aligned architecture artifact required by the assignment."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "architecture.pdf"
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontSize=8.5, leading=11))
styles.add(ParagraphStyle(name="Flow", parent=styles["BodyText"], fontSize=9, leading=12, alignment=1, textColor=colors.HexColor("#123047")))
styles["Title"].fontSize = 25
styles["Title"].leading = 30
styles["Heading1"].textColor = colors.HexColor("#003C5A")


def make_table(rows, widths):
    result = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003C5A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C8D1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EDF5F8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return result


story = [
    Paragraph("GraphOne / FrontierAtlas", styles["Title"]),
    Paragraph("PRD-Aligned Global AI Intelligence Platform Architecture", styles["Heading2"]),
    Spacer(1, 5 * mm),
    Paragraph("Purpose", styles["Heading1"]),
    Paragraph("A scalable Python intelligence-ingestion backend for startups, products, research papers, repository metrics, fresh AI news, and fresh AI jobs. The architecture follows the supplied PRD: FastAPI, asynchronous crawling, Celery/Redis, PostgreSQL with pgvector, S3-compatible raw evidence storage, Neo4j, Pydantic, Docker, and structured logs.", styles["BodyText"]),
    Spacer(1, 4 * mm),
    Paragraph("Logical flow", styles["Heading1"]),
]
flow_items = ["Authorized source configuration", "Celery scheduler + Redis queue", "Async httpx crawling workers", "MinIO / S3 raw HTML and text evidence", "Content cleaning + 24-hour freshness gate", "Grounded LLM extraction: Gemini → Groq → DeepSeek", "Pydantic schema validation + canonical entity resolution", "PostgreSQL + pgvector (source of truth)", "Neo4j relationship projection", "FastAPI, CSV exports, Google Sheets webhook"]
flow_rows = []
for index, item in enumerate(flow_items):
    flow_rows.append([Paragraph(item, styles["Flow"])])
    if index < len(flow_items) - 1:
        flow_rows.append([Paragraph("↓", styles["Flow"])])
flow = Table(flow_rows, colWidths=[170 * mm], hAlign="CENTER")
flow.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF7FA")),
    ("BOX", (0, 0), (0, -1), 0.75, colors.HexColor("#0E6385")),
    ("INNERGRID", (0, 0), (0, -1), 0.3, colors.HexColor("#B7C8D1")),
    ("TOPPADDING", (0, 0), (0, -1), 4), ("BOTTOMPADDING", (0, 0), (0, -1), 4),
]))
story += [flow, PageBreak(), Paragraph("Data, quality, and resilience", styles["Heading1"])]

rows = [["Component", "PRD-aligned responsibility"]]
for left, right in [
    ("FastAPI", "Authenticated source, job, record, GitHub-metric, CSV, Sheets, and health endpoints."),
    ("Celery + Redis", "Durable asynchronous job dispatch, periodic source scheduling, retries, late acknowledgement, and horizontal worker scale."),
    ("PostgreSQL + pgvector", "Source-of-truth records, provenance, task state, entity mappings, uniqueness constraints, and semantic embedding column."),
    ("MinIO / S3", "Immutable raw HTML/text capture keyed by SHA-256, separate from structured intelligence."),
    ("Neo4j", "Retryable projection of record-to-entity relationships; graph outages do not lose PostgreSQL data."),
    ("LLM orchestrator", "Provider fallback, semantic chunking, JSON-only source-grounded extraction, 429/413 handling."),
]:
    rows.append([Paragraph(left, styles["Tiny"]), Paragraph(right, styles["Tiny"])])
story += [make_table(rows, [52 * mm, 118 * mm]), Spacer(1, 5 * mm), Paragraph("Safety and correctness controls", styles["Heading1"])]
for item in [
    "Every record stores source URL, source identity, raw-document linkage, provider, collection timestamp, validation state, and normalized UTC dates.",
    "News and job records are fresh only when published within the prior 24 hours. Unavailable or implausible dates are UNVERIFIED, never silently fresh.",
    "Unique dedupe keys plus idempotency keys stop repeated ingestion. Entity aliases are mapped conservatively; uncertain matches are marked for review.",
    "HTTP 429 receives exponential retry/backoff; oversized LLM input is sentence-chunked for 413 avoidance. 401/403/CAPTCHA sources are put in NEEDS_REVIEW, never bypassed.",
    "All source collection must be authorized. The product does not evade site access controls or manufacture missing facts.",
]:
    story.append(Paragraph("• " + item, styles["BodyText"]))

story += [PageBreak(), Paragraph("Deployment and scale", styles["Heading1"])]
rows = [["Layer", "Local Docker service", "Scale-out direction"]]
for row in [
    ("API", "FastAPI + Uvicorn", "Stateless replicas behind a TLS load balancer"),
    ("Workers", "Celery worker + beat", "Independent workers, queues, priorities, and autoscaling"),
    ("Data", "PostgreSQL pgvector", "Managed HA PostgreSQL, partition/archive historical collections"),
    ("Evidence", "MinIO", "S3-compatible object storage lifecycle and retention rules"),
    ("Graph", "Neo4j Community", "Managed/cluster Neo4j for larger relationship exploration"),
    ("Operations", "Docker Compose", "Secrets manager, monitoring, backups, SLOs, alerts, CI/CD"),
]:
    rows.append([Paragraph(value, styles["Tiny"]) for value in row])
story += [make_table(rows, [35 * mm, 65 * mm, 70 * mm]), Spacer(1, 6 * mm), Paragraph("Runbook", styles["Heading1"])]
story.append(Paragraph("Copy .env.example to .env, change secrets, then run docker compose up --build -d. Initialize and seed via the API container, configure permitted sources, and monitor the worker. Full commands are in SETUP_AND_RUN.txt.", styles["BodyText"]))

SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=17 * mm, bottomMargin=17 * mm, title="GraphOne Architecture").build(story)
print(OUT)


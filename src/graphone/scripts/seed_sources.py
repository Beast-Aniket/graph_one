import asyncio
from sqlalchemy import select
from graphone.db import SessionLocal
from graphone.models import CanonicalEntity, Source
from graphone.services.entities import normalize_name

ENTITY_SEEDS = {
    "OpenAI": ["Open AI", "OpenAI Inc.", "OpenAI, Inc."],
    "Anthropic": ["Anthropic PBC"],
    "Google DeepMind": ["DeepMind", "Google Deepmind"],
    "Hugging Face": ["HuggingFace"],
    "Mistral AI": ["Mistral"],
    "Cohere": ["Cohere Inc."],
    "Perplexity": ["Perplexity AI"],
    "xAI": ["X.AI"],
    "Stability AI": ["StabilityAI"],
    "Scale AI": ["ScaleAI"],
}


async def seed() -> None:
    async with SessionLocal() as session:
        for canonical_name, aliases in ENTITY_SEEDS.items():
            key = normalize_name(canonical_name)
            existing = await session.scalar(select(CanonicalEntity).where(CanonicalEntity.canonical_key == key))
            if not existing:
                session.add(CanonicalEntity(canonical_name=canonical_name, canonical_key=key, aliases=aliases, is_seed=True))
        for kind, label in (("NEWS", "AI News Source"), ("JOB", "AI Job Board")):
            for number in range(1, 6):
                name = f"{label} {number}"
                url = f"https://example.invalid/{kind.lower()}-{number}.rss"
                existing = await session.scalar(select(Source).where(Source.name == name, Source.base_url == url))
                if not existing:
                    session.add(Source(
                        name=name,
                        base_url=url,
                        source_type=kind,
                        parser_type="RSS",
                        parser_config={"notes": "Disabled template. Replace with an authorized RSS/API endpoint before enabling."},
                        enabled=False,
                    ))
        for name, url, source_type in [
            ("AI Startup Directory", "https://example.invalid/ai-startups", "STARTUP"),
            ("AI Product Directory", "https://example.invalid/ai-products", "PRODUCT"),
            ("AI Research Repository", "https://example.invalid/ai-research", "RESEARCH_PAPER"),
        ]:
            existing = await session.scalar(select(Source).where(Source.name == name, Source.base_url == url))
            if not existing:
                session.add(Source(
                    name=name,
                    base_url=url,
                    source_type=source_type,
                    parser_type="LLM",
                    parser_config={"notes": "Disabled template. Replace with an authorized source and configure an extraction provider."},
                    enabled=False,
                ))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
    print("Canonical entity seeds and five-news/five-job source templates are ready.")


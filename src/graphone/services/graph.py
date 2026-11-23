import asyncio
from neo4j import AsyncGraphDatabase
from graphone.config import get_settings


class RelationshipGraph:
    """Neo4j projection of durable PostgreSQL records; PostgreSQL remains the source of truth."""

    async def upsert_record(self, record_id: str, record_type: str, entity: str | None, title: str | None) -> None:
        if not entity and not title:
            return
        settings = get_settings()
        driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password))
        try:
            async with driver.session() as session:
                await session.run(
                    "MERGE (r:Record {id: $id}) "
                    "SET r.record_type = $record_type, r.title = $title "
                    "WITH r "
                    "FOREACH (_ IN CASE WHEN $entity IS NULL THEN [] ELSE [1] END | "
                    "MERGE (e:Entity {name: $entity}) MERGE (r)-[:ABOUT]->(e))",
                    id=record_id,
                    record_type=record_type,
                    entity=entity,
                    title=title,
                )
        finally:
            await driver.close()


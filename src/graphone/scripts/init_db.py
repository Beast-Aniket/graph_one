import asyncio
from graphone.db import initialize_database


if __name__ == "__main__":
    asyncio.run(initialize_database())
    print("PostgreSQL schema and pgvector extension are ready.")


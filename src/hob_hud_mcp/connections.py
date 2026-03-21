"""
Database connection managers for hob_hud_mcp.
All three connections are initialised once at server startup via FastMCP lifespan
and shared across all tool calls through the lifespan state.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from neo4j import AsyncGraphDatabase, AsyncDriver
from qdrant_client import AsyncQdrantClient

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass
class Connections:
    mongo: MongoClient
    mongo_db: Database
    neo4j: AsyncDriver
    qdrant: AsyncQdrantClient
    qdrant_default_collection: str
    embedding_model: str


@asynccontextmanager
async def lifespan(_app: Any):
    """
    Open all three DB connections at startup, yield the shared state,
    close cleanly on shutdown.
    """
    mongo_uri = _optional("MONGO_URI", "mongodb://localhost:27017")
    mongo_client: MongoClient = MongoClient(mongo_uri)
    mongo_client.admin.command("ping")
    mongo_db_name = _optional("MONGO_DB", "hob_hud")
    mongo_db = mongo_client[mongo_db_name]

    neo4j_driver = AsyncGraphDatabase.driver(
        _optional("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            _optional("NEO4J_USERNAME", "neo4j"),
            _optional("NEO4J_PASSWORD", "password"),
        ),
        database=_optional("NEO4J_DATABASE", "neo4j"),
    )
    await neo4j_driver.verify_connectivity()

    qdrant_local = _optional("QDRANT_LOCAL_PATH")
    if qdrant_local:
        qdrant_client = AsyncQdrantClient(path=qdrant_local)
    else:
        qdrant_client = AsyncQdrantClient(
            url=_optional("QDRANT_URL", "http://localhost:6333"),
            api_key=_optional("QDRANT_API_KEY") or None,
        )

    connections = Connections(
        mongo=mongo_client,
        mongo_db=mongo_db,
        neo4j=neo4j_driver,
        qdrant=qdrant_client,
        qdrant_default_collection=_optional("QDRANT_DEFAULT_COLLECTION", "hob_hud"),
        embedding_model=_optional(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
    )

    try:
        yield {"connections": connections}
    finally:
        mongo_client.close()
        await neo4j_driver.close()
        await qdrant_client.close()
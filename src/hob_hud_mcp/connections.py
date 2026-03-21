"""
Database connection managers for hob_hud_mcp.
All three connections are initialised once at server startup via FastMCP lifespan
and shared across all tool calls through the lifespan state.

Neo4j and Qdrant failures are non-fatal: the server starts with those set to None
and the relevant tools return a clear error message rather than crashing.
"""

from __future__ import annotations

import os
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from neo4j import AsyncGraphDatabase, AsyncDriver
from qdrant_client import AsyncQdrantClient

load_dotenv()


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass
class Connections:
    mongo: MongoClient
    mongo_db: Database
    neo4j: Optional[AsyncDriver]           # None if auth failed
    neo4j_error: str
    qdrant: Optional[AsyncQdrantClient]    # None if locked/unavailable
    qdrant_error: str
    qdrant_default_collection: str
    embedding_model: str



@asynccontextmanager
async def lifespan(_app: Any):
    """
    Open all three DB connections at startup, yield the shared state,
    close cleanly on shutdown. Neo4j and Qdrant failures are non-fatal.
    """
    # ── MongoDB ────────────────────────────────────────────────────────────────
    mongo_uri = _optional("MONGO_URI", "mongodb://localhost:27017")
    mongo_client: MongoClient = MongoClient(mongo_uri)
    mongo_client.admin.command("ping")
    mongo_db = mongo_client[_optional("MONGO_DB", "hob_hud")]

    # ── Neo4j (non-fatal) ──────────────────────────────────────────────────────
    neo4j_driver: Optional[AsyncDriver] = None
    neo4j_error = ""
    try:
        driver = AsyncGraphDatabase.driver(
            _optional("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                _optional("NEO4J_USERNAME", "neo4j"),
                _optional("NEO4J_PASSWORD", "neo4j"),
            ),
            database=_optional("NEO4J_DATABASE", "neo4j"),
        )
        await driver.verify_connectivity()
        neo4j_driver = driver
    except Exception as exc:
        neo4j_error = str(exc)
        warnings.warn(
            f"[hob_hud] Neo4j unavailable — hud_graph and hud_relate will "
            f"return errors until fixed. Reason: {neo4j_error}",
            RuntimeWarning,
            stacklevel=2,
        )

    # ── Qdrant (non-fatal) ─────────────────────────────────────────────────────
    qdrant_client: Optional[AsyncQdrantClient] = None
    qdrant_error = ""
    try:
        qdrant_local = _optional("QDRANT_LOCAL_PATH")
        if qdrant_local:
            qdrant_client = AsyncQdrantClient(path=qdrant_local)
        else:
            qdrant_client = AsyncQdrantClient(
                url=_optional("QDRANT_URL", "http://localhost:6333"),
                api_key=_optional("QDRANT_API_KEY") or None,
            )
    except Exception as exc:
        qdrant_error = str(exc)
        warnings.warn(
            f"[hob_hud] Qdrant unavailable — hud_vector and hud_search (semantic) "
            f"will return errors until fixed. Reason: {qdrant_error}",
            RuntimeWarning,
            stacklevel=2,
        )

    connections = Connections(
        mongo=mongo_client,
        mongo_db=mongo_db,
        neo4j=neo4j_driver,
        neo4j_error=neo4j_error,
        qdrant=qdrant_client,
        qdrant_error=qdrant_error,
        qdrant_default_collection=_optional("QDRANT_DEFAULT_COLLECTION", "hob_hud"),
        embedding_model=_optional(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
    )

    try:
        yield {"connections": connections}
    finally:
        mongo_client.close()
        if neo4j_driver:
            await neo4j_driver.close()
        if qdrant_client:
            await qdrant_client.close()

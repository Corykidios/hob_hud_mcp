"""
hob_hud_mcp — Cori's MCP server. Mercury/Air/Hill.
GraphRAG hybrid retrieval: Neo4j + Qdrant + Mistral embeddings.
"""

import sys
import os
import json
import logging
from typing import Optional

# Pull in graphrag-hybrid source directly
sys.path.insert(0, r'C:/c/apps/servers/graphrag-hybrid/src')

from dotenv import load_dotenv
load_dotenv(r'C:/c/apps/servers/hob_hud_mcp/.env')

from fastmcp import FastMCP
from mistral_embedder import MistralEmbedder

from database.neo4j_manager import Neo4jManager
from database.qdrant_manager import QdrantManager
from query_engine import QueryEngine

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# --- Config shim (matches the config.get() interface the managers expect) ---
class Cfg:
    def __init__(self):
        self._d = {
            "neo4j": {
                "uri": os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                "http_uri": os.environ.get("NEO4J_HTTP_URI", "http://localhost:7474"),
                "username": os.environ.get("NEO4J_USERNAME", "neo4j"),
                "password": os.environ.get("NEO4J_PASSWORD", "password"),
                "database": os.environ.get("NEO4J_DATABASE", "neo4j"),
            },
            "qdrant": {
                "host": os.environ.get("QDRANT_HOST", "localhost"),
                "port": int(os.environ.get("QDRANT_PORT", 6333)),
                "grpc_port": int(os.environ.get("QDRANT_GRPC_PORT", 6334)),
                "prefer_grpc": os.environ.get("QDRANT_PREFER_GRPC", "true").lower() == "true",
                "collection": os.environ.get("QDRANT_COLLECTION", "document_chunks"),
            },
            "embedding": {
                "model_name": os.environ.get("EMBEDDING_MODEL_NAME", "mistral-embed"),
                "vector_size": int(os.environ.get("EMBEDDING_VECTOR_SIZE", 1024)),
                "device": "api",
                "max_length": int(os.environ.get("EMBEDDING_MAX_LENGTH", 512)),
            },
        }

    def get(self, key: str, default=None):
        parts = key.split(".")
        val = self._d
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return default
            if val is None:
                return default
        return val

# --- Initialize ---
config = Cfg()
embedder = MistralEmbedder()
neo4j = Neo4jManager(config)
neo4j.connect()
qdrant = QdrantManager(config, embedding_model=embedder)
qdrant.connect()
engine = QueryEngine(neo4j, qdrant, embedding_processor=embedder)

mcp = FastMCP("hob_hud")

# --- Tools ---

@mcp.tool()
def hybrid_search(query: str, limit: int = 5, category: Optional[str] = None) -> str:
    """Semantic + graph hybrid search. Best for exploratory retrieval."""
    results = engine.hybrid_search(query, limit=limit, category=category)
    return json.dumps(results, indent=2, default=str)

@mcp.tool()
def semantic_search(query: str, limit: int = 5, category: Optional[str] = None) -> str:
    """Pure vector similarity search against Qdrant."""
    results = engine.semantic_search(query, limit=limit, category=category)
    return json.dumps(results, indent=2, default=str)

@mcp.tool()
def suggest_related(doc_id: str, limit: int = 5) -> str:
    """Find documents related to a given doc via graph connections."""
    results = engine.suggest_related(doc_id, limit=limit)
    return json.dumps(results, indent=2, default=str)

@mcp.tool()
def get_categories() -> str:
    """List all document categories in the graph."""
    results = engine.get_all_categories()
    return json.dumps(results, indent=2, default=str)

@mcp.tool()
def get_statistics() -> str:
    """Full system stats: Neo4j node/rel counts, Qdrant vector counts."""
    results = engine.get_statistics()
    return json.dumps(results, indent=2, default=str)

@mcp.tool()
def read_neo4j_cypher(query: str, params: Optional[str] = None) -> str:
    """Run a read-only Cypher query against Neo4j. params as JSON string."""
    p = json.loads(params) if params else {}
    with neo4j.driver.session() as session:
        result = session.run(query, p)
        records = [dict(r) for r in result]
    return json.dumps(records, indent=2, default=str)

@mcp.tool()
def write_neo4j_cypher(query: str, params: Optional[str] = None) -> str:
    """Run a write Cypher query against Neo4j. params as JSON string."""
    p = json.loads(params) if params else {}
    with neo4j.driver.session() as session:
        result = session.run(query, p)
        summary = result.consume()
        return json.dumps({"counters": dict(summary.counters)}, indent=2, default=str)

@mcp.tool()
def get_neo4j_schema() -> str:
    """Get current Neo4j schema: labels, relationship types, constraints."""
    with neo4j.driver.session() as session:
        labels = session.run("CALL db.labels()").data()
        rel_types = session.run("CALL db.relationshipTypes()").data()
    return json.dumps({"labels": labels, "relationship_types": rel_types}, indent=2, default=str)

@mcp.tool()
def qdrant_list_collections() -> str:
    """List all collections in Qdrant."""
    collections = qdrant.client.get_collections()
    return json.dumps([c.name for c in collections.collections], indent=2)

@mcp.tool()
def qdrant_collection_info(collection_name: str) -> str:
    """Get info on a specific Qdrant collection."""
    info = qdrant.client.get_collection(collection_name)
    return json.dumps(str(info), indent=2)

if __name__ == "__main__":
    mcp.run()
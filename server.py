"""
hob_hud_mcp — Heads-Up Display for AI database access.

10 tools across two databases:

  GraphRAG (3):   ask_graph_rag, ingest_to_graph, clear_graph
  Neo4j (3):      neo4j_schema, neo4j_read, neo4j_write
  Qdrant (4):     qdrant_collections, qdrant_store, qdrant_search, qdrant_points

Designed to be registered as a single MCP server in Claude Desktop or Letta.
Connection config via environment variables or a .env file at ENV_PATH below.
"""

import os
import sys
import json
import uuid
from typing import Optional

from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

# Point this at your .env or set variables directly in the environment
ENV_PATH = os.getenv("HOB_HUD_ENV", r"C:\c\apps\Qdrant-Neo4j-Ollama-Graph-Rag\.env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

# Needed for graph_rag imports to resolve relative paths
GRAPH_RAG_DIR = os.getenv("HOB_HUD_GRAPH_RAG_DIR", r"C:\c\apps\Qdrant-Neo4j-Ollama-Graph-Rag")
if GRAPH_RAG_DIR not in sys.path:
    sys.path.insert(0, GRAPH_RAG_DIR)
os.chdir(GRAPH_RAG_DIR)

# ── Imports ───────────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase, exceptions as neo4j_exc
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)
from openai import OpenAI

from graph_rag import (
    initialize_clients,
    create_collection,
    retriever_search,
    fetch_related_graph,
    format_graph_context,
    graphRAG_run,
    extract_graph_components_parallel,
    ingest_to_neo4j,
    ingest_to_qdrant,
    clear_data,
)
from processors.processor_factory import get_processor, reload_config

# ── Connections ───────────────────────────────────────────────────────────────

# Neo4j
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "morpheus4j")

# Qdrant
QDRANT_HOST    = os.getenv("QDRANT_HOST",    "localhost")
QDRANT_PORT    = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)

# Embeddings (NIM or OpenAI-compatible)
EMBED_MODEL    = os.getenv("OPENAI_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
EMBED_DIM      = int(os.getenv("OPENAI_VECTOR_DIMENSION", "1024"))
OPENAI_KEY     = os.getenv("OPENAI_API_KEY", "")
OPENAI_URL     = os.getenv("OPENAI_BASE_URL", None)

# Direct DB clients (for Neo4j + Qdrant tools)
neo4j_driver  = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
qdrant        = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY)
embed_client  = OpenAI(api_key=OPENAI_KEY, base_url=OPENAI_URL) if OPENAI_URL else OpenAI(api_key=OPENAI_KEY)

# GraphRAG clients (shared collection)
gr_neo4j, gr_qdrant, gr_collection = initialize_clients()
_, vector_dimension = reload_config()
get_processor()
create_collection(gr_qdrant, gr_collection, vector_dimension)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float]:
    resp = embed_client.embeddings.create(input=text, model=EMBED_MODEL)
    return resp.data[0].embedding


def _cypher(query: str, params: dict, write: bool) -> str:
    try:
        with neo4j_driver.session() as session:
            result = session.run(query, params)
            records = [dict(r) for r in result]
            out = {"records": records}
            if write:
                c = result.consume().counters
                out["counters"] = {k: v for k, v in vars(c).items() if not k.startswith("_") and v}
            return json.dumps(out, default=str)
    except neo4j_exc.CypherSyntaxError as e:
        return f"Cypher syntax error: {e.message}"
    except neo4j_exc.ClientError as e:
        return f"Neo4j client error: {e.message}"
    except Exception as e:
        return f"Neo4j error: {e}"


# ── Server ────────────────────────────────────────────────────────────────────

mcp = FastMCP("hob_hud")


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH RAG  —  high-level knowledge graph pipeline
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def ask_graph_rag(query: str) -> str:
    """Query the Neo4j+Qdrant knowledge graph. Use for questions about ingested documents, entities, or relationships."""
    try:
        retriever_result = retriever_search(gr_neo4j, gr_qdrant, gr_collection, query)
        if not hasattr(retriever_result, 'items') or not retriever_result.items:
            return "No results found in the knowledge base."
        entity_ids = [item.content.split("'id': '")[1].split("'")[0] for item in retriever_result.items]
        subgraph = fetch_related_graph(gr_neo4j, entity_ids)
        graph_context = format_graph_context(subgraph)
        return str(graphRAG_run(graph_context, query, stream=False))
    except Exception as e:
        return f"Error querying GraphRAG: {e}"


@mcp.tool()
def ingest_to_graph(text: str) -> str:
    """Save new text permanently into the knowledge graph (Neo4j + Qdrant). Use when given facts or documents to remember."""
    try:
        if not text.strip():
            return "Error: empty text."
        nodes, relationships = extract_graph_components_parallel(text, chunk_size=5000, max_workers=4)
        node_id_mapping = ingest_to_neo4j(gr_neo4j, nodes, relationships, batch_size=100)
        ingest_to_qdrant(gr_qdrant, gr_collection, text, node_id_mapping)
        return f"Ingested {len(nodes)} nodes and {len(relationships)} relationships."
    except Exception as e:
        return f"Error ingesting: {e}"


@mcp.tool()
def clear_graph() -> str:
    """Wipe all data from the GraphRAG Neo4j and Qdrant stores. Only use if explicitly asked to reset."""
    try:
        clear_data(gr_neo4j, gr_qdrant, gr_collection)
        return "Knowledge graph cleared."
    except Exception as e:
        return f"Error clearing: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# NEO4J  —  direct Cypher access
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def neo4j_schema() -> str:
    """
    Return Neo4j schema: labels, relationship types, property keys, indexes,
    constraints. Call this before writing Cypher to understand what exists.
    """
    fallback = """
    CALL db.labels() YIELD label WITH collect(label) AS labels
    CALL db.relationshipTypes() YIELD relationshipType WITH labels, collect(relationshipType) AS rels
    CALL db.propertyKeys() YIELD propertyKey WITH labels, rels, collect(propertyKey) AS props
    RETURN labels, rels AS relationship_types, props AS property_keys
    """
    try:
        with neo4j_driver.session() as session:
            try:
                records = [dict(r) for r in session.run("CALL apoc.meta.schema() YIELD value RETURN value")]
            except Exception:
                records = [dict(r) for r in session.run(fallback)]
            indexes = [dict(r) for r in session.run("SHOW INDEXES")]
            constraints = [dict(r) for r in session.run("SHOW CONSTRAINTS")]
        return json.dumps({"schema": records, "indexes": indexes, "constraints": constraints}, default=str)
    except Exception as e:
        return f"Schema error: {e}"


@mcp.tool()
def neo4j_read(cypher: str, params: Optional[str] = None) -> str:
    """
    Execute a READ-ONLY Cypher query (MATCH, RETURN, WITH, CALL read procs).
    params: optional JSON string e.g. '{"name": "Alice"}'.
    """
    return _cypher(cypher, json.loads(params) if params else {}, write=False)


@mcp.tool()
def neo4j_write(cypher: str, params: Optional[str] = None) -> str:
    """
    Execute a WRITE Cypher query (CREATE, MERGE, SET, DELETE, REMOVE).
    params: optional JSON string e.g. '{"name": "Alice", "age": 30}'.
    Returns affected record counts.
    """
    return _cypher(cypher, json.loads(params) if params else {}, write=True)


# ══════════════════════════════════════════════════════════════════════════════
# QDRANT  —  direct vector store access
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def qdrant_collections(
    operation: str,
    collection_name: Optional[str] = None,
    distance: Optional[str] = "Cosine",
) -> str:
    """
    Manage Qdrant collections.
    operation = 'list'   — list all collections.
    operation = 'info'   — details for collection_name.
    operation = 'create' — create collection_name (distance: Cosine/Dot/Euclid).
    operation = 'delete' — permanently delete collection_name and all its points.
    """
    try:
        if operation == "list":
            return json.dumps([c.name for c in qdrant.get_collections().collections])
        elif operation == "info":
            return json.dumps(qdrant.get_collection(collection_name).model_dump(), default=str)
        elif operation == "create":
            dist_map = {"Cosine": Distance.COSINE, "Dot": Distance.DOT, "Euclid": Distance.EUCLID}
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=dist_map.get(distance, Distance.COSINE)),
            )
            return f"Collection '{collection_name}' created (dim={EMBED_DIM}, distance={distance})."
        elif operation == "delete":
            qdrant.delete_collection(collection_name)
            return f"Collection '{collection_name}' deleted."
        else:
            return f"Unknown operation '{operation}'. Use: list, info, create, delete."
    except Exception as e:
        return f"qdrant_collections error: {e}"


@mcp.tool()
def qdrant_store(
    collection_name: str,
    text: str,
    metadata: Optional[str] = None,
) -> str:
    """
    Embed text and store it as a point in a Qdrant collection.
    metadata: optional JSON string e.g. '{"persona": "Nyx", "platform": "Claude", "year": "2024"}'.
    Auto-creates the collection if it does not exist. Returns the point ID.
    """
    try:
        existing = [c.name for c in qdrant.get_collections().collections]
        if collection_name not in existing:
            qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )
        vector = _embed(text)
        payload = json.loads(metadata) if metadata else {}
        payload["text"] = text
        point_id = str(uuid.uuid4())
        qdrant.upsert(
            collection_name=collection_name,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
        return json.dumps({"id": point_id, "collection": collection_name})
    except Exception as e:
        return f"qdrant_store error: {e}"


@mcp.tool()
def qdrant_search(
    collection_name: str,
    query: str,
    limit: int = 10,
    filter_json: Optional[str] = None,
) -> str:
    """
    Semantic search in a Qdrant collection.
    Returns top `limit` results with payload and similarity score.
    filter_json: optional filter e.g. '{"must": [{"key": "persona", "match": {"value": "Nyx"}}]}'.
    """
    try:
        vector = _embed(query)
        search_filter = None
        if filter_json:
            f = json.loads(filter_json)
            must = [FieldCondition(key=c["key"], match=MatchValue(value=c["match"]["value"])) for c in f.get("must", [])]
            search_filter = Filter(must=must) if must else None
        results = qdrant.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )
        return json.dumps([{"id": r.id, "score": r.score, "payload": r.payload} for r in results], default=str)
    except Exception as e:
        return f"qdrant_search error: {e}"


@mcp.tool()
def qdrant_points(
    operation: str,
    collection_name: str,
    point_ids: Optional[str] = None,
    limit: int = 20,
    offset: Optional[str] = None,
) -> str:
    """
    Direct point operations on a Qdrant collection (no embedding involved).
    operation = 'count'  — total points in collection.
    operation = 'get'    — retrieve points by IDs (point_ids: JSON array).
    operation = 'scroll' — page through all points (limit, offset: last ID from previous scroll).
    operation = 'delete' — delete points by IDs (point_ids: JSON array).
    """
    try:
        if operation == "count":
            return json.dumps({"count": qdrant.get_collection(collection_name).points_count})
        elif operation == "get":
            points = qdrant.retrieve(collection_name=collection_name, ids=json.loads(point_ids), with_payload=True)
            return json.dumps([{"id": p.id, "payload": p.payload} for p in points], default=str)
        elif operation == "scroll":
            results, next_offset = qdrant.scroll(
                collection_name=collection_name, limit=limit, offset=offset,
                with_payload=True, with_vectors=False,
            )
            return json.dumps({"points": [{"id": p.id, "payload": p.payload} for p in results], "next_offset": next_offset}, default=str)
        elif operation == "delete":
            ids = json.loads(point_ids)
            qdrant.delete(collection_name=collection_name, points_selector=ids)
            return f"Deleted {len(ids)} point(s) from '{collection_name}'."
        else:
            return f"Unknown operation '{operation}'. Use: count, get, scroll, delete."
    except Exception as e:
        return f"qdrant_points error: {e}"


if __name__ == "__main__":
    mcp.run()

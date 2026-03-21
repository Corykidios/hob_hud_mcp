"""
hob_hud_mcp — Corpus Intelligence MCP Server
Three databases, ten tools, one purpose: make sense of vast corpora.

Raw layer  (full DB access):  hud_mongo · hud_graph · hud_vector
Pipeline   (research workflows): hud_ingest · hud_search · hud_extract
                                  hud_relate · hud_order · hud_annotate · hud_report
"""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from .connections import lifespan
from .tools.raw_mongo import HudMongoInput, run_hud_mongo
from .tools.raw_graph import HudGraphInput, run_hud_graph
from .tools.raw_vector import HudVectorInput, run_hud_vector
from .tools.pipeline_ingest import HudIngestInput, run_hud_ingest
from .tools.pipeline_tools import (
    HudSearchInput, run_hud_search,
    HudExtractInput, run_hud_extract,
    HudRelateInput, run_hud_relate,
    HudOrderInput, run_hud_order,
    HudAnnotateInput, run_hud_annotate,
    HudReportInput, run_hud_report,
)

mcp = FastMCP("hob_hud_mcp", lifespan=lifespan)


@mcp.tool(name="hud_mongo", annotations={"title": "MongoDB Raw Access", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
async def hud_mongo(params: HudMongoInput, ctx: Context) -> str:
    """
    Full MongoDB access via operation routing.
    Covers all document CRUD, aggregation, text search, schema inference, index and collection management.
    Args: params (HudMongoInput). Returns: str JSON.
    """
    return await run_hud_mongo(params, ctx)


@mcp.tool(name="hud_graph", annotations={"title": "Neo4j Graph Raw Access", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
async def hud_graph(params: HudGraphInput, ctx: Context) -> str:
    """
    Full Neo4j access via operation routing.
    Execute arbitrary Cypher (read or write), introspect schema, list GDS procedures.
    Args: params (HudGraphInput). Returns: str JSON.
    """
    return await run_hud_graph(params, ctx)


@mcp.tool(name="hud_vector", annotations={"title": "Qdrant Vector Raw Access", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False})
async def hud_vector(params: HudVectorInput, ctx: Context) -> str:
    """
    Full Qdrant vector database access via operation routing.
    Store text with metadata (auto-embeds locally), retrieve by semantic similarity, manage collections.
    Args: params (HudVectorInput). Returns: str JSON.
    """
    return await run_hud_vector(params, ctx)


@mcp.tool(name="hud_ingest", annotations={"title": "Corpus Ingestion", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True})
async def hud_ingest(params: HudIngestInput, ctx: Context) -> str:
    """
    Load documents from files and directories into the corpus.
    Auto-detects format (JSON exports, Markdown, JSONL, CSV, plain text). Skips already-ingested files by default.
    Args: params (HudIngestInput). Returns: str JSON.
    """
    return await run_hud_ingest(params, ctx)


@mcp.tool(name="hud_search", annotations={"title": "Corpus Search", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def hud_search(params: HudSearchInput, ctx: Context) -> str:
    """
    Retrieve documents from the corpus using keyword, semantic, or hybrid search.
    Keyword uses MongoDB text indexes. Semantic uses Qdrant + fastembed (local). Hybrid combines both.
    Args: params (HudSearchInput). Returns: str JSON.
    """
    return await run_hud_search(params, ctx)


@mcp.tool(name="hud_extract", annotations={"title": "Entity and Term Extraction", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def hud_extract(params: HudExtractInput, ctx: Context) -> str:
    """
    Extract named entities and terms from corpus documents.
    Catalogues people, places, concepts, works with occurrence references. Supports alias merging.
    Args: params (HudExtractInput). Returns: str JSON.
    """
    return await run_hud_extract(params, ctx)


@mcp.tool(name="hud_relate", annotations={"title": "Graph Relationship Management", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def hud_relate(params: HudRelateInput, ctx: Context) -> str:
    """
    Create and query relationships between entities in the Neo4j graph.
    Supports path finding, neighborhood traversal, and custom Cypher patterns.
    Args: params (HudRelateInput). Returns: str JSON.
    """
    return await run_hud_relate(params, ctx)


@mcp.tool(name="hud_order", annotations={"title": "Temporal Ordering", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def hud_order(params: HudOrderInput, ctx: Context) -> str:
    """
    Assign and query temporal metadata. Dual-date model: created_date (when written) and
    referenced_period (what era it discusses). Query each independently.
    Args: params (HudOrderInput). Returns: str JSON.
    """
    return await run_hud_order(params, ctx)


@mcp.tool(name="hud_annotate", annotations={"title": "Annotation and Named Collections", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False})
async def hud_annotate(params: HudAnnotateInput, ctx: Context) -> str:
    """
    Tag documents, add notes, and curate named collections.
    Human-in-the-loop layer for building exemplar sets, bibliographies, thematic clusters.
    Args: params (HudAnnotateInput). Returns: str JSON.
    """
    return await run_hud_annotate(params, ctx)


@mcp.tool(name="hud_report", annotations={"title": "Corpus Reports and Export", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
async def hud_report(params: HudReportInput, ctx: Context) -> str:
    """
    Generate statistics, summaries, comparisons, and exports from the corpus.
    Provides corpus overviews, source comparisons, and JSON or Markdown exports.
    Args: params (HudReportInput). Returns: str JSON or Markdown.
    """
    return await run_hud_report(params, ctx)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
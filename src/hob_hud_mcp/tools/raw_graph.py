"""
hud_graph — full Neo4j surface via operation routing.
Wraps neo4j/mcp capabilities: arbitrary Cypher read/write, schema introspection.
"""

from __future__ import annotations

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from ..utils import err, get_connections, ok

GRAPH_OPERATIONS = (
    "read_cypher   — execute a read-only Cypher query",
    "write_cypher  — execute a write Cypher query (CREATE, MERGE, SET, DELETE, etc.)",
    "get_schema    — introspect node labels, relationship types, and property keys",
    "list_gds      — list available Graph Data Science procedures (if GDS installed)",
)


class HudGraphInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    operation: str = Field(
        ...,
        description=(
            "Neo4j operation to perform. Valid values:\n"
            + "\n".join(f"  {op}" for op in GRAPH_OPERATIONS)
        ),
    )
    cypher: str = Field(
        default="",
        description="Cypher query string. Required for read_cypher and write_cypher.",
    )
    params: str = Field(
        default="{}",
        description="JSON object of Cypher query parameters, e.g. '{\"name\": \"Meri\"}'.",
    )
    limit: int = Field(
        default=100,
        description="Maximum number of rows to return for read queries.",
        ge=1,
        le=10000,
    )


async def run_hud_graph(params: HudGraphInput, ctx: Context) -> str:
    import json

    conns = get_connections(ctx)
    if conns.neo4j is None:
        return err(
            "Neo4j is not connected.",
            f"Fix the password in .env (NEO4J_PASSWORD) and restart. Detail: {conns.neo4j_error}",
        )
    op = params.operation.strip().lower()

    try:
        cypher_params = json.loads(params.params or "{}")

        if op == "get_schema":
            schema_cypher = """
            CALL apoc.meta.schema()
            YIELD value
            RETURN value
            """
            async with conns.neo4j.session() as session:
                result = await session.run(schema_cypher)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "list_gds":
            async with conns.neo4j.session() as session:
                result = await session.run(
                    "CALL gds.list() YIELD name, description RETURN name, description"
                )
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "read_cypher":
            if not params.cypher:
                return err("'cypher' is required for read_cypher")
            cypher = params.cypher
            if "limit" not in cypher.lower():
                cypher = f"{cypher.rstrip()} LIMIT {params.limit}"
            async with conns.neo4j.session() as session:
                result = await session.run(cypher, cypher_params)
                records = [dict(r) async for r in result]
            return ok(records)

        if op == "write_cypher":
            if not params.cypher:
                return err("'cypher' is required for write_cypher")
            async with conns.neo4j.session() as session:
                result = await session.run(params.cypher, cypher_params)
                summary = await result.consume()
            return ok({
                "nodes_created": summary.counters.nodes_created,
                "nodes_deleted": summary.counters.nodes_deleted,
                "relationships_created": summary.counters.relationships_created,
                "relationships_deleted": summary.counters.relationships_deleted,
                "properties_set": summary.counters.properties_set,
            })

        return err(
            f"Unknown operation: '{op}'",
            "Valid operations: read_cypher, write_cypher, get_schema, list_gds",
        )

    except Exception as e:
        return err(str(e))
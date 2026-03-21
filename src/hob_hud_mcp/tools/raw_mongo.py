"""
hud_mongo — full MongoDB surface via operation routing.
Wraps the capabilities of furey/mongodb-lens into a single Letta-compatible tool.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from ..utils import err, get_connections, ok

MONGO_OPERATIONS = (
    "find            — query documents (filter, projection, sort, limit, skip)",
    "find_one        — fetch a single document by filter",
    "insert          — insert one or many documents",
    "update          — update documents matching a filter",
    "delete          — delete documents matching a filter",
    "aggregate       — run an aggregation pipeline",
    "count           — count documents matching a filter",
    "text_search     — full-text search across text-indexed fields",
    "explain         — explain query execution plan",
    "export          — export query results as JSON or CSV",
    "schema          — infer the schema of a collection",
    "stats           — database or collection statistics",
    "indexes         — list or create indexes on a collection",
    "create_collection — create a new collection",
    "drop_collection — drop a collection (destructive)",
    "list_collections — list all collections in current database",
    "list_databases  — list all accessible databases",
    "use_database    — switch active database context",
)


class HudMongoInput(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    operation: str = Field(
        ...,
        description=(
            "MongoDB operation to perform. Valid values:\n"
            + "\n".join(f"  {op}" for op in MONGO_OPERATIONS)
        ),
    )
    database: str = Field(default="", description="Database name. Uses the default configured DB if omitted.")
    collection: str = Field(default="", description="Collection name. Required for document-level operations.")
    filter: str = Field(default="{}", description="JSON filter/query document.")
    document: str = Field(default="", description="JSON document(s) for insert/update.")
    pipeline: str = Field(default="[]", description="JSON aggregation pipeline array.")
    projection: str = Field(default="{}", description="JSON projection document.")
    sort: str = Field(default="{}", description="JSON sort document, e.g. '{\"date\": -1}'.")
    limit: int = Field(default=20, description="Maximum number of documents to return.", ge=1, le=10000)
    skip: int = Field(default=0, description="Number of documents to skip (pagination).", ge=0)
    query_text: str = Field(default="", description="Plain-text search string for 'text_search'.")
    index_spec: str = Field(default="", description="JSON index spec for 'indexes', e.g. '{\"field\": 1}'.")
    export_format: str = Field(default="json", description="Export format: 'json' or 'csv'.")
    upsert: bool = Field(default=False, description="Insert if no match found during update.")
    multi: bool = Field(default=True, description="Update/delete all matches if true, first only if false.")


async def run_hud_mongo(params: HudMongoInput, ctx: Context) -> str:
    """Route to the correct MongoDB operation."""
    conns = get_connections(ctx)
    db = conns.mongo[params.database] if params.database else conns.mongo_db
    op = params.operation.strip().lower()

    try:
        filter_doc: dict = json.loads(params.filter or "{}")
        projection_doc: dict = json.loads(params.projection or "{}") or None
        sort_doc: dict = json.loads(params.sort or "{}")

        if op == "list_databases":
            return ok(conns.mongo.list_database_names())

        if op == "use_database":
            if not params.database:
                return err("'database' is required for use_database")
            conns.mongo_db = conns.mongo[params.database]
            return ok(f"Active database set to '{params.database}'")

        if op == "list_collections":
            return ok(db.list_collection_names())

        if op == "create_collection":
            if not params.collection:
                return err("'collection' is required")
            db.create_collection(params.collection)
            return ok(f"Collection '{params.collection}' created.")

        if op == "drop_collection":
            if not params.collection:
                return err("'collection' is required")
            db.drop_collection(params.collection)
            return ok(f"Collection '{params.collection}' dropped.")

        if op == "stats":
            if params.collection:
                result = db.command("collStats", params.collection)
            else:
                result = db.command("dbStats")
            return ok(result)

        if op == "schema":
            if not params.collection:
                return err("'collection' is required for schema inference")
            sample = list(db[params.collection].find({}, limit=100))
            schema: dict[str, set] = {}
            for doc in sample:
                for key, val in doc.items():
                    schema.setdefault(key, set()).add(type(val).__name__)
            return ok({k: list(v) for k, v in schema.items()})

        if op == "indexes":
            if not params.collection:
                return err("'collection' is required for index operations")
            coll = db[params.collection]
            if params.index_spec:
                spec = json.loads(params.index_spec)
                name = coll.create_index(list(spec.items()))
                return ok(f"Index created: {name}")
            return ok(list(coll.index_information().values()))

        if op == "count":
            if not params.collection:
                return err("'collection' is required for count")
            return ok(db[params.collection].count_documents(filter_doc))

        if op == "find":
            if not params.collection:
                return err("'collection' is required for find")
            cursor = db[params.collection].find(filter_doc, projection_doc or None)
            if sort_doc:
                cursor = cursor.sort(list(sort_doc.items()))
            cursor = cursor.skip(params.skip).limit(params.limit)
            return ok(list(cursor))

        if op == "find_one":
            if not params.collection:
                return err("'collection' is required for find_one")
            result = db[params.collection].find_one(filter_doc, projection_doc or None)
            return ok(result)

        if op == "insert":
            if not params.collection or not params.document:
                return err("'collection' and 'document' are required for insert")
            docs = json.loads(params.document)
            coll = db[params.collection]
            if isinstance(docs, list):
                result = coll.insert_many(docs)
                return ok({"inserted_ids": [str(i) for i in result.inserted_ids]})
            result = coll.insert_one(docs)
            return ok({"inserted_id": str(result.inserted_id)})

        if op == "update":
            if not params.collection or not params.document:
                return err("'collection' and 'document' (update spec) are required")
            update_doc = json.loads(params.document)
            coll = db[params.collection]
            if params.multi:
                result = coll.update_many(filter_doc, update_doc, upsert=params.upsert)
            else:
                result = coll.update_one(filter_doc, update_doc, upsert=params.upsert)
            return ok({
                "matched": result.matched_count,
                "modified": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            })

        if op == "delete":
            if not params.collection:
                return err("'collection' is required for delete")
            coll = db[params.collection]
            result = coll.delete_many(filter_doc) if params.multi else coll.delete_one(filter_doc)
            return ok({"deleted": result.deleted_count})

        if op == "aggregate":
            if not params.collection:
                return err("'collection' is required for aggregate")
            pipeline = json.loads(params.pipeline or "[]")
            return ok(list(db[params.collection].aggregate(pipeline)))

        if op == "text_search":
            if not params.collection or not params.query_text:
                return err("'collection' and 'query_text' are required for text_search")
            result = list(db[params.collection].find(
                {"$text": {"$search": params.query_text}},
                {**({} if not projection_doc else projection_doc), "score": {"$meta": "textScore"}},
                limit=params.limit,
            ))
            return ok(result)

        if op == "explain":
            if not params.collection:
                return err("'collection' is required for explain")
            plan = db.command("explain", {"find": params.collection, "filter": filter_doc})
            return ok(plan)

        if op == "export":
            if not params.collection:
                return err("'collection' is required for export")
            docs = list(db[params.collection].find(filter_doc, projection_doc or None).limit(params.limit))
            if params.export_format == "csv" and docs:
                import csv, io
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=list(docs[0].keys()))
                writer.writeheader()
                writer.writerows(docs)
                return ok({"format": "csv", "data": buf.getvalue()})
            return ok({"format": "json", "data": docs})

        return err(
            f"Unknown operation: '{op}'",
            "See the 'operation' field description for the full list of valid operations.",
        )

    except json.JSONDecodeError as e:
        return err(f"JSON parse error: {e}", "Ensure filter/document/pipeline fields contain valid JSON.")
    except Exception as e:
        return err(str(e))
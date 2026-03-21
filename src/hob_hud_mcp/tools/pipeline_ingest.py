"""
hud_ingest — source-agnostic document loading.
Reads files and directories into MongoDB, detecting format automatically.
Supports: plain text, JSON (ChatGPT/Claude exports), Markdown, JSONL, CSV.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from ..utils import err, get_connections, ok

INGEST_OPERATIONS = (
    "load_file       — load a single file into the corpus",
    "load_directory  — load all supported files from a directory",
    "preview         — preview a file's detected format without ingesting",
    "status          — count of ingested documents per source",
    "list_sources    — list all distinct source labels in the corpus",
    "remove_source   — delete all documents with a given source label",
)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".jsonl", ".csv"}


class HudIngestInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    operation: str = Field(
        ...,
        description=("Ingest operation to perform. Valid values:\n" + "\n".join(f"  {op}" for op in INGEST_OPERATIONS)),
    )
    path: str = Field(default="", description="Absolute path to a file or directory.")
    source_label: str = Field(default="", description="Source label e.g. 'claude', 'chatgpt'. Auto-derived from filename if omitted.")
    collection: str = Field(default="corpus", description="MongoDB collection to store ingested documents in.")
    format_hint: str = Field(default="", description="Optional: 'conversation', 'academic', 'notes', 'raw'.")
    recursive: bool = Field(default=True, description="Recurse into subdirectories for load_directory.")
    overwrite: bool = Field(default=False, description="Re-ingest already-present files if true.")


async def run_hud_ingest(params: HudIngestInput, ctx: Context) -> str:
    conns = get_connections(ctx)
    op = params.operation.strip().lower()
    coll = conns.mongo_db[params.collection]

    try:
        if op == "status":
            pipeline = [{"$group": {"_id": "$_source", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
            return ok(list(coll.aggregate(pipeline)))

        if op == "list_sources":
            return ok(coll.distinct("_source"))

        if op == "remove_source":
            if not params.source_label:
                return err("'source_label' is required for remove_source")
            result = coll.delete_many({"_source": params.source_label})
            return ok({"deleted": result.deleted_count, "source": params.source_label})

        if op == "preview":
            if not params.path:
                return err("'path' is required for preview")
            p = Path(params.path)
            if not p.exists():
                return err(f"Path not found: {params.path}")
            if p.is_file():
                return ok({"file": str(p), "detected_format": _detect_format(p), "sample": _read_sample(p)})
            if p.is_dir():
                files = _list_files(p, params.recursive)
                return ok({"directory": str(p), "supported_files": len(files), "files": [str(f) for f in files[:20]]})
            return err("Path is neither a file nor a directory.")

        if op == "load_file":
            if not params.path:
                return err("'path' is required for load_file")
            p = Path(params.path)
            if not p.exists() or not p.is_file():
                return err(f"File not found: {params.path}")
            label = params.source_label or p.stem
            if not params.overwrite and coll.count_documents({"_source_file": str(p)}):
                return ok({"skipped": True, "reason": "already ingested", "file": str(p)})
            docs = _parse_file(p, label, params.format_hint)
            if docs:
                coll.insert_many(docs)
            return ok({"ingested": len(docs), "source": label, "file": str(p)})

        if op == "load_directory":
            if not params.path:
                return err("'path' is required for load_directory")
            p = Path(params.path)
            if not p.exists() or not p.is_dir():
                return err(f"Directory not found: {params.path}")
            files = _list_files(p, params.recursive)
            total, skipped = 0, 0
            for f in files:
                label = params.source_label or p.name
                if not params.overwrite and coll.count_documents({"_source_file": str(f)}):
                    skipped += 1
                    continue
                docs = _parse_file(f, label, params.format_hint)
                if docs:
                    coll.insert_many(docs)
                    total += len(docs)
            return ok({"ingested": total, "files_processed": len(files) - skipped, "files_skipped": skipped})

        return err(f"Unknown operation: '{op}'", "Valid: load_file, load_directory, preview, status, list_sources, remove_source")

    except Exception as e:
        return err(str(e))


def _list_files(directory: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return [f for f in directory.glob(pattern) if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, list) and data and "role" in str(data[0]):
                return "conversation_json"
            if isinstance(data, dict) and "mapping" in data:
                return "chatgpt_export"
            return "json"
        except Exception:
            return "json_malformed"
    if suffix == ".jsonl": return "jsonl"
    if suffix == ".md": return "markdown"
    if suffix == ".csv": return "csv"
    return "plain_text"


def _read_sample(path: Path, lines: int = 5) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:lines])
    except Exception as e:
        return f"[could not read: {e}]"


def _parse_file(path: Path, source_label: str, format_hint: str) -> list[dict]:
    fmt = format_hint or _detect_format(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    base = {"_source": source_label, "_source_file": str(path), "_format": fmt}

    if fmt == "conversation_json":
        try:
            turns = json.loads(text)
            return [{**base, "_type": "turn", **turn} for turn in turns if isinstance(turn, dict)]
        except Exception:
            pass

    if fmt == "chatgpt_export":
        try:
            data = json.loads(text)
            docs = []
            for node in data.get("mapping", {}).values():
                msg = node.get("message")
                if msg and msg.get("content"):
                    content = msg["content"]
                    text_parts = content.get("parts", []) if isinstance(content, dict) else []
                    docs.append({**base, "_type": "turn",
                                 "role": msg.get("author", {}).get("role", "unknown"),
                                 "content": " ".join(str(p) for p in text_parts),
                                 "create_time": msg.get("create_time")})
            return docs
        except Exception:
            pass

    if fmt == "jsonl":
        docs = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                try:
                    docs.append({**base, **json.loads(line)})
                except Exception:
                    pass
        return docs

    if fmt == "csv":
        import csv, io
        return [{**base, **row} for row in csv.DictReader(io.StringIO(text))]

    return [{**base, "_type": "document", "content": text, "filename": path.name}]
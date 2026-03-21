"""
Shared utility functions for hob_hud_mcp tools.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context

from .connections import Connections


def get_connections(ctx: Context) -> Connections:
    """Pull the shared Connections object from lifespan state."""
    return ctx.request_context.lifespan_state["connections"]


def ok(data: Any) -> str:
    """Serialise a successful result to a JSON string."""
    return json.dumps({"status": "ok", "result": data}, indent=2, default=str)


def err(message: str, hint: str = "") -> str:
    """Serialise an error with an optional actionable hint."""
    payload: dict[str, str] = {"status": "error", "message": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, indent=2)
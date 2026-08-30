# @file MCP stdio adapter over the public application API.
# @domain interfaces
# @status stable
# @adr [[0009-capability-projection]]
# @adr [[0012-exact-human-approval]]
# @tested-by [[test_public_surfaces.py]]
"""Minimal JSON-RPC MCP stdio adapter over the public application API."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from spire.core import SpireError
from spire.surfaces import PublicApi


def _customer_schema() -> dict[str, Any]:
    return {"type": "object", "required": ["customer_id"], "properties": {"customer_id": {"type": "string"}}}


TOOLS = (
    ("auth_status", "Return local Google Ads authentication status.", {"type": "object", "properties": {}}),
    ("accounts_list", "List accessible Google Ads accounts.", {"type": "object", "properties": {}}),
    ("account_refresh", "Explicitly refresh frozen account truth.", {"type": "object", "required": ["customer_id"], "properties": {"customer_id": {"type": "string"}, "campaign_id": {"type": "string"}, "enabled_only": {"type": "boolean"}, "date_range": {"type": "object"}}}),
    ("campaigns_discover", "Discover live campaigns for an account.", _customer_schema()),
    ("campaigns_list", "List campaigns from the frozen catalog.", _customer_schema()),
    ("campaigns_get", "Read one campaign from the current snapshot.", {"type": "object", "required": ["customer_id", "campaign_id"], "properties": {"customer_id": {"type": "string"}, "campaign_id": {"type": "string"}}}),
    ("evidence_query", "Query safe frozen evidence.", {"type": "object", "required": ["customer_id", "campaign_ids", "dataset"], "properties": {"customer_id": {"type": "string"}, "campaign_ids": {"type": "array", "items": {"type": "string"}}, "dataset": {"type": "string"}, "date_range": {"type": "object"}, "dimensions": {"type": "array", "items": {"type": "string"}}, "metrics": {"type": "array", "items": {"type": "string"}}, "filters": {"type": "object"}, "limit": {"type": "integer"}, "order_by": {"type": ["string", "array"]}}}),
    ("evidence_datasets", "List logical datasets in the current snapshot.", {"type": "object", "required": ["customer_id", "campaign_id"], "properties": {"customer_id": {"type": "string"}, "campaign_id": {"type": "string"}}}),
    ("change_budget", "Prepare an UPDATE_BUDGET run; production stops for human approval.", {"type": "object", "required": ["customer_id", "campaign_id", "daily_budget", "environment"], "properties": {"customer_id": {"type": "string"}, "campaign_id": {"type": "string"}, "daily_budget": {}, "environment": {"type": "string"}}}),
    ("runs_list", "Discover execution runs through safe public projections.", {"type": "object", "properties": {"customer_id": {"type": "string"}, "campaign_id": {"type": "string"}, "status": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}, "latest": {"type": "boolean"}, "order_by": {"type": "string", "enum": ["created_at", "updated_at"]}}}),
    ("run_get", "Inspect an execution run.", {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}),
    ("run_resume", "Resume an already human-approved run.", {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}),
)


class McpServer:
    def __init__(self, api: PublicApi) -> None:
        self.api = api

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._result(request_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "spire", "version": "0.1.0"}})
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": [{"name": name, "description": description, "inputSchema": schema} for name, description, schema in TOOLS]})
        if method == "tools/call":
            return self._call(request_id, message.get("params") or {})
        return self._error(request_id, -32601, "METHOD_NOT_FOUND")

    def _call(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = self._dispatch(name, arguments)
            text = json.dumps(result, sort_keys=True, default=str)
            return self._result(request_id, {"content": [{"type": "text", "text": text}], "structuredContent": result, "isError": False})
        except (SpireError, ValueError, TypeError, OSError, KeyError) as exc:
            code = getattr(exc, "reason_code", None) or (
                "PROVIDER_UNAVAILABLE" if isinstance(exc, OSError) else str(exc)
            ) or type(exc).__name__
            payload = {"error": code}
            return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload, "isError": True})

    def _dispatch(self, name: str, args: dict[str, Any]) -> Any:
        if name == "auth_status":
            return self.api.application.auth.status()
        if name == "accounts_list":
            return self.api.accounts_list()
        if name == "account_refresh":
            return self.api.account_refresh(args["customer_id"], campaign_id=args.get("campaign_id"), enabled_only=args.get("enabled_only", False), date_range=args.get("date_range"))
        if name == "campaigns_discover":
            return self.api.campaigns_discover(args["customer_id"])
        if name == "campaigns_list":
            return self.api.campaigns_list(args["customer_id"])
        if name == "campaigns_get":
            return self.api.campaigns_get(args["customer_id"], args["campaign_id"])
        if name == "evidence_query":
            return self.api.evidence_query(args["customer_id"], args["campaign_ids"], args["dataset"], date_range=args.get("date_range"), dimensions=args.get("dimensions", ()), metrics=args.get("metrics", ()), filters=args.get("filters", {}), limit=args.get("limit", 100), order_by=args.get("order_by"))
        if name == "evidence_datasets":
            return self.api.evidence_datasets(args["customer_id"], args["campaign_id"])
        if name == "change_budget":
            return self.api.change_budget(args["customer_id"], args["campaign_id"], args["daily_budget"], environment=args["environment"])
        if name == "runs_list":
            return self.api.runs_list(
                customer_id=args.get("customer_id"),
                campaign_id=args.get("campaign_id"),
                state=args.get("status"),
                order_by=args.get("order_by", "created_at"),
                limit=args.get("limit", 100),
                latest=args.get("latest", False),
            )
        if name == "run_get":
            return self.api.run_get(args["run_id"])
        if name == "run_resume":
            return self.api.run_resume(args["run_id"])
        raise ValueError("MCP_TOOL_NOT_FOUND")

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(application, *, input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
    server = McpServer(PublicApi(application))
    for line in input_stream:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = server.handle(message)
        except (TypeError, ValueError, json.JSONDecodeError):
            response = server._error(None, -32700, "PARSE_ERROR")
        if response is not None:
            output_stream.write(json.dumps(response, sort_keys=True) + "\n")
            output_stream.flush()

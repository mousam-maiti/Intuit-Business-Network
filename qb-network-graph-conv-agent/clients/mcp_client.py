"""
MCP Protocol client — connects to qb-network-graph-mcp-servers via Streamable HTTP.

Usage:
    client = MCPToolClient("http://localhost:8081/mcp")
    await client.connect()
    result = await client.call_tool("search_entities", {"query": "plumbing"})
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Error returned by MCP server tool call."""
    pass


class MCPToolClient:
    """MCP client that calls tools on the remote MCP server via Streamable HTTP."""

    def __init__(self, url: str = "http://localhost:8081/mcp", timeout_ms: int = 30000):
        self.url = url
        self._timeout = timeout_ms / 1000.0
        self._session_id: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._request_id = 0
        self._tool_names: list[str] = []

    @property
    def connected(self) -> bool:
        return self._session_id is not None

    async def connect(self):
        """Initialize MCP session via Streamable HTTP handshake."""
        self._client = httpx.AsyncClient(timeout=self._timeout)

        # Step 1: initialize
        result = await self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "conversational-agent", "version": "1.0.0"},
        })
        server_name = result.get("serverInfo", {}).get("name", "unknown")
        logger.info(f"MCP session: {self._session_id} → {server_name}")

        # Step 2: initialized notification
        await self._notify("notifications/initialized")

        # Step 3: verify tools
        tools_result = await self._rpc("tools/list", {})
        self._tool_names = [t["name"] for t in tools_result.get("tools", [])]
        logger.info(f"MCP tools: {len(self._tool_names)} available")

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call an MCP tool and return the parsed result.

        Auto-reconnects once if the MCP session has expired.
        """
        try:
            return await self._call_tool_inner(name, arguments)
        except MCPError as e:
            if "Session not found" in str(e):
                logger.warning("MCP session expired — reconnecting...")
                await self._reconnect()
                return await self._call_tool_inner(name, arguments)
            raise

    async def _call_tool_inner(self, name: str, arguments: dict) -> Any:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})

        if result.get("isError"):
            text = result["content"][0]["text"] if result.get("content") else "Unknown error"
            raise MCPError(f"{name}: {text}")

        content = result["content"][0]["text"]
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return content

    async def _reconnect(self):
        """Re-initialize the MCP session after expiration."""
        self._session_id = None
        try:
            await self.connect()
            logger.info("MCP session re-established successfully")
        except Exception as e:
            logger.error(f"MCP reconnection failed: {e}")
            raise MCPError(f"MCP reconnection failed: {e}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self._session_id = None

    # ── Internal ─────────────────────────────────────────────

    async def _rpc(self, method: str, params: dict) -> dict:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        response = await self._client.post(self.url, json=payload, headers=headers)

        if "mcp-session-id" in response.headers:
            self._session_id = response.headers["mcp-session-id"]

        # Parse SSE response (event: message\r\ndata: {...}\r\n)
        for line in response.text.replace("\r\n", "\n").split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                data = json.loads(line[6:])
                if "error" in data:
                    raise MCPError(data["error"].get("message", str(data["error"])))
                return data.get("result", {})

        # Direct JSON fallback
        data = response.json()
        if "error" in data:
            raise MCPError(data["error"].get("message", str(data["error"])))
        return data.get("result", {})

    async def _notify(self, method: str, params: dict | None = None):
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        await self._client.post(self.url, json=payload, headers=headers)

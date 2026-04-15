"""Environment MCP server wrapping live context functions."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.services.live_context_service import get_live_context as build_live_context


class EnvironmentMCPServer:
    """FastMCP wrapper exposing environment-aware context tools."""

    def __init__(self) -> None:
        self.mcp = FastMCP("environment-context")
        self._register_tools()

    def _register_tools(self) -> None:
        @self.mcp.tool()
        def get_live_context(preferred_location: dict[str, Any] | None = None) -> dict[str, Any]:
            """Return current date, solar term, location and weather context."""
            return build_live_context(preferred_location=preferred_location)


environment_mcp_server = EnvironmentMCPServer()
mcp = environment_mcp_server.mcp


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

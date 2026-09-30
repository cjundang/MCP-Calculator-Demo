"""MCP server #1 — Addition only. Exposes a single tool: add.

Runs over TCP using the transport/host/port from .env (via config.py).
"""

import argparse
import os
import sys

# Allow importing config.py from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

mcp = MCPServer("add-server")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers (a + b)."""
    return a + b


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=config.MCP_HOST)
    parser.add_argument("--port", type=int, default=config.ADD_PORT)
    args = parser.parse_args()
    mcp.run(transport=config.MCP_TRANSPORT, host=args.host, port=args.port)

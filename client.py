"""
MCP client that uses an OpenRouter LLM to parse a text message and pick which
MCP server/tool to call.

Architecture
------------
There are 4 independent MCP servers, each exposing exactly ONE tool and each
listening on its own TCP port (streamable-http transport):

    servers/add_server.py       -> tool "add"       -> http://127.0.0.1:8001/mcp
    servers/subtract_server.py  -> tool "subtract"  -> http://127.0.0.1:8002/mcp
    servers/multiply_server.py  -> tool "multiply"  -> http://127.0.0.1:8003/mcp
    servers/divide_server.py    -> tool "divide"    -> http://127.0.0.1:8004/mcp

Start the servers first (see start_servers.py or the README), then run this
client. The client connects to each server over TCP.

The client:
  1. Connects to all 4 servers over TCP (streamable-http) and lists each one's tools.
  2. Builds an OpenAI-style "tools" schema from every tool it discovered,
     remembering which server each tool lives on.
  3. Sends the user's message + tool schema to an OpenRouter LLM.
  4. The LLM decides which tool to call and with what arguments (this IS the
     server-selection step). The client routes that call to the owning server.
  5. Returns the computed result.

Because each tool lives on a different server, choosing a tool == choosing a
server. The mapping is printed so you can see how selection happened.

Usage:
    python client.py "12 + 3"
    python client.py "หาผลบวกของ 5 และ 7"
    python client.py            # interactive mode; 'exit' to quit

LLM provider selection:
    Primary  : local Ollama (Qwen) via its OpenAI-compatible endpoint.
    Fallback : OpenRouter, used automatically when Ollama is not reachable.

Configuration:
    All tunable values live in `.env` and are loaded via config.py.
    See `.env` for the full list (LLM endpoints/models, MCP host/ports,
    HTTP path, transport, DEBUG, system prompt, timeouts).
"""

import asyncio
import json
import sys
import urllib.request

from openai import OpenAI

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import config

DEBUG = config.DEBUG
SYSTEM_PROMPT = config.SYSTEM_PROMPT

# Each entry: (label, TCP URL of the server's streamable-http endpoint).
SERVERS = [
    (label, config.server_url(port)) for label, port in config.SERVER_REGISTRY
]


def debug(msg):
    """Print a DEBUG line only when DEBUG is enabled."""
    if DEBUG:
        print(f"  [DEBUG] {msg}")


def ollama_available(timeout=None):
    """Return True if a local Ollama server responds on its /v1 endpoint."""
    if timeout is None:
        timeout = config.OLLAMA_PROBE_TIMEOUT
    # OLLAMA_BASE_URL ends with /v1; probe its /models list.
    url = config.OLLAMA_BASE_URL.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as e:
        debug(f"Ollama probe failed: {e}")
        return False


def select_llm():
    """Choose the LLM provider: Ollama first, then OpenRouter fallback.

    Returns (client, model, provider_label) or raises SystemExit if neither
    is usable.
    """
    # 1) Primary: local Ollama running Qwen.
    if ollama_available():
        client = OpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")  # key unused
        return client, config.OLLAMA_MODEL, f"ollama ({config.OLLAMA_MODEL})"

    print("Ollama not reachable — falling back to OpenRouter.")

    # 2) Fallback: OpenRouter (needs an API key).
    if not config.OPENROUTER_KEY:
        print(
            "Ollama is unavailable and OPENROUTER_KEY is not set. "
            "Cannot reach any LLM provider."
        )
        sys.exit(1)

    client = OpenAI(base_url=config.OPENROUTER_BASE_URL, api_key=config.OPENROUTER_KEY)
    return client, config.OPENROUTER_MODEL, f"openrouter ({config.OPENROUTER_MODEL})"


class Connection:
    """Holds a live MCP session for one server plus its context managers."""

    def __init__(self, label, session, tools, _ctx):
        self.label = label
        self.session = session
        self.tools = tools
        self._ctx = _ctx


async def open_servers(stack):
    """Connect to every server over TCP, initialize a session, list its tools.

    Returns:
        connections: list[Connection]
        tool_to_conn: dict[tool_name -> Connection]
        openai_tools: list[dict]  (OpenAI tool schema for the LLM)
    """
    connections = []
    tool_to_conn = {}
    openai_tools = []

    for label, url in SERVERS:
        # Connect over TCP using the streamable-http transport.
        streams = await stack.enter_async_context(streamable_http_client(url))
        read, write = streams[0], streams[1]
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        listed = await session.list_tools()
        conn = Connection(label, session, listed.tools, None)
        connections.append(conn)

        for tool in listed.tools:
            tool_to_conn[tool.name] = conn
            # Field is input_schema in mcp 2.x (inputSchema in 1.x).
            schema = getattr(tool, "input_schema", None) or getattr(
                tool, "inputSchema", {}
            )
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": schema,
                    },
                }
            )

    return connections, tool_to_conn, openai_tools


def choose_tool_with_llm(client, model, message, openai_tools):
    """Ask the LLM which tool to call. Returns (tool_name, arguments dict)."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        tools=openai_tools,
        tool_choice="required",  # force a tool call
    )

    choice = response.choices[0].message

    # DEBUG: show what the LLM returned before we parse it.
    debug(f"model={response.model} finish_reason={response.choices[0].finish_reason}")
    debug(f"raw content={choice.content!r}")
    debug(f"tool_calls={choice.tool_calls!r}")
    if getattr(response, "usage", None) is not None:
        debug(f"token usage={response.usage}")

    if not choice.tool_calls:
        raise RuntimeError(f"LLM did not select a tool. Said: {choice.content!r}")

    call = choice.tool_calls[0]
    args = json.loads(call.function.arguments or "{}")

    # DEBUG: show the parsed decision returned by this function.
    debug(f"chosen tool name  = {call.function.name!r}")
    debug(f"raw arguments str = {call.function.arguments!r}")
    debug(f"parsed arguments  = {args!r}")

    return call.function.name, args


async def call_tool(conn, tool_name, args):
    """Invoke a tool on its owning server and extract a readable result."""
    result = await conn.session.call_tool(tool_name, args)
    parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    value = ", ".join(parts) if parts else str(result.content)

    is_error = getattr(result, "is_error", None)
    if is_error is None:
        is_error = getattr(result, "isError", False)
    return value, bool(is_error)


async def handle(client, model, tool_to_conn, openai_tools, message):
    tool_name, args = choose_tool_with_llm(client, model, message, openai_tools)
    conn = tool_to_conn.get(tool_name)
    if conn is None:
        print(f"  LLM picked unknown tool '{tool_name}'")
        return

    # Show the routing decision so server selection is visible.
    print(f"  LLM selected tool : {tool_name}")
    print(f"  routed to server  : {conn.label}")
    print(f"  arguments         : {args}")

    value, is_error = await call_tool(conn, tool_name, args)
    if is_error:
        print(f"  result            : ERROR - {value}")
    else:
        print(f"  result            : {value}")


async def run(messages):
    # Pick the LLM: Ollama (Qwen) first, OpenRouter as fallback.
    client, model, provider = select_llm()

    # AsyncExitStack keeps all 4 server sessions open together.
    from contextlib import AsyncExitStack

    async with AsyncExitStack() as stack:
        connections, tool_to_conn, openai_tools = await open_servers(stack)

        print("Connected to servers and discovered tools:")
        for conn in connections:
            names = ", ".join(t.name for t in conn.tools)
            print(f"  - {conn.label}: [{names}]")
        print(f"\nUsing LLM provider: {provider}\n")

        if messages:
            for msg in messages:
                print(f"> {msg}")
                try:
                    await handle(client, model, tool_to_conn, openai_tools, msg)
                except Exception as e:
                    print(f"  error: {e}")
                print()
        else:
            print("Type a message (e.g. '12 + 3'). Type 'exit' to quit.")
            loop = asyncio.get_event_loop()
            while True:
                msg = await loop.run_in_executor(None, input, "> ")
                if msg.strip().lower() in {"exit", "quit", "q"}:
                    break
                try:
                    await handle(client, model, tool_to_conn, openai_tools, msg)
                except Exception as e:
                    print(f"  error: {e}")


def main():
    messages = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else []
    asyncio.run(run(messages))


if __name__ == "__main__":
    main()

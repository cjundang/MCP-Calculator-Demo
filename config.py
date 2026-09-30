"""
Central configuration for the MCP Calculator Demo.

All fixed/tunable values are defined in `.env` and loaded here once. Every other
module (client.py, servers/*.py, start_servers.py) imports from this module so
there is a single source of truth. Defaults mirror the values in .env so the
code still runs if a key is missing.
"""

import os

from dotenv import load_dotenv

# Load .env from the project root regardless of the current working directory.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)


def _bool(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


# --- Primary LLM: local Ollama ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_PROBE_TIMEOUT = float(os.getenv("OLLAMA_PROBE_TIMEOUT", "2.0"))

# --- Fallback LLM: OpenRouter ---
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")

# --- MCP servers (TCP / streamable-http) ---
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")
MCP_HTTP_PATH = os.getenv("MCP_HTTP_PATH", "/mcp")

ADD_PORT = int(os.getenv("ADD_PORT", "8001"))
SUBTRACT_PORT = int(os.getenv("SUBTRACT_PORT", "8002"))
MULTIPLY_PORT = int(os.getenv("MULTIPLY_PORT", "8003"))
DIVIDE_PORT = int(os.getenv("DIVIDE_PORT", "8004"))

# --- Launcher ---
SERVER_SHUTDOWN_TIMEOUT = float(os.getenv("SERVER_SHUTDOWN_TIMEOUT", "5"))

# --- Behavior ---
DEBUG = _bool(os.getenv("DEBUG", ""))
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a calculator router. The user sends a message in Thai or English "
    "describing a single arithmetic operation on two numbers. Call exactly one "
    "of the provided tools with the two numbers as `a` and `b`, preserving their "
    "order as written. Do not answer in text; always call a tool.",
)


def server_url(port):
    """Build a server's streamable-http URL from host/path config."""
    return f"http://{MCP_HOST}:{port}{MCP_HTTP_PATH}"


# Central registry: (label, port). Ordering defines display order.
SERVER_REGISTRY = [
    ("add-server", ADD_PORT),
    ("subtract-server", SUBTRACT_PORT),
    ("multiply-server", MULTIPLY_PORT),
    ("divide-server", DIVIDE_PORT),
]

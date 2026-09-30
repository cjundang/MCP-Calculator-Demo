"""
Start all 4 MCP servers over TCP, each on its own port.

All values (host, ports, shutdown timeout) come from .env via config.py.

Usage:
    python start_servers.py

Press Ctrl+C to stop them all.
"""

import signal
import subprocess
import sys

import config

# Map each server label to its script path.
SCRIPTS = {
    "add-server": "servers/add_server.py",
    "subtract-server": "servers/subtract_server.py",
    "multiply-server": "servers/multiply_server.py",
    "divide-server": "servers/divide_server.py",
}


def main():
    procs = []
    try:
        for label, port in config.SERVER_REGISTRY:
            path = SCRIPTS[label]
            print(f"Starting {path} on {config.MCP_HOST}:{port} ...")
            p = subprocess.Popen(
                [sys.executable, path, "--host", config.MCP_HOST, "--port", str(port)]
            )
            procs.append(p)

        print("\nAll servers running. Press Ctrl+C to stop.\n")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping servers ...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
        for p in procs:
            try:
                p.wait(timeout=config.SERVER_SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()

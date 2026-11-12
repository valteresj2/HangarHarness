"""Tiny stdio MCP server used by the benchmark and the tests (no dependencies)."""
import json
import sys

SECRETS = {"alfa": "HNGR-7Q4X-ALFA-2291", "beta": "HNGR-0M1Z-BETA-5530"}
TOOLS = [
    {"name": "get_secret", "description": "Return the secret stored in a named vault.",
     "inputSchema": {"type": "object", "properties": {"vault": {"type": "string", "description": "vault name"}}, "required": ["vault"]}},
    {"name": "list_vaults", "description": "List the vault names.", "inputSchema": {"type": "object", "properties": {}}},
]

for line in sys.stdin:
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        continue
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "vault", "version": "1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name == "list_vaults":
            text, err = ", ".join(SECRETS), False
        elif name == "get_secret" and args.get("vault") in SECRETS:
            text, err = SECRETS[args["vault"]], False
        else:
            text, err = f"unknown vault or tool: {name} {args}", True
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)

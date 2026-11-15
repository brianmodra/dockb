#!/usr/bin/env bash
# Call the MCP list_tools against the public listener.
#
# Mints a fresh per-prompt token (the live-token map is in the server's memory,
# so every run mints a new one).

set -euo pipefail

cd "$(dirname "$0")/.."          # the repo root (the .env lives there)
source .venv/bin/activate

: "${DOCKB_SECRET_KEY:?DOCKB_SECRET_KEY must be set (it is in .env)}"

ACCOUNT_ID="${1:-ac0bb3e8-ff1f-46a8-ab2e-1b89649600a8}"
MCP_URL="${MCP_URL:-http://127.0.0.1:8001/mcp}"

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/mcp/mint \
  -H "X-MCP-Mint-Secret: $DOCKB_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"prompt_id\": \"prompt-$RANDOM\", \"account_id\": \"$ACCOUNT_ID\"}" \
  | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

python - "$TOKEN" "$MCP_URL" <<'EOF'
import asyncio
import json
import sys

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

token, mcp_url = sys.argv[1], sys.argv[2]

async def main() -> None:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(600.0, connect=10.0),
    ) as http_client:
        async with streamable_http_client(mcp_url, http_client=http_client) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()

                result = await session.list_tools()
                for tool in result.tools:
                    print(tool.name)
                    print(tool.description)
                    print(tool.input_schema)
                #print(json.dumps(json.loads(result.content[0].text), indent=2))


asyncio.run(main())
EOF

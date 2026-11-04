#!/usr/bin/env bash
# Call the MCP find_paragraphs tool against the public listener.
#
# Mints a fresh per-prompt token (the live-token map is in the server's memory,
# so every run mints a new one), then calls the tool with the criteria below.
# Edit the DOCUMENT_ID and CRITERIA to change the query.

set -euo pipefail

cd "$(dirname "$0")/.."          # the repo root (the .env lives there)
source .venv/bin/activate

: "${DOCKB_SECRET_KEY:?DOCKB_SECRET_KEY must be set (it is in .env)}"

ACCOUNT_ID="${1:-ac0bb3e8-ff1f-46a8-ab2e-1b89649600a8}"
DOCUMENT_ID="${2:-6bd0e68d-1635-48bd-9838-71747306234b}"
MCP_URL="${MCP_URL:-http://127.0.0.1:8001/mcp}"

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/mcp/mint \
  -H "X-MCP-Mint-Secret: $DOCKB_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"prompt_id\": \"prompt-$RANDOM\", \"account_id\": \"$ACCOUNT_ID\"}" \
  | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

python - "$TOKEN" "$DOCUMENT_ID" "$MCP_URL" <<'EOF'
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

token, document_id, mcp_url = sys.argv[1], sys.argv[2], sys.argv[3]

CRITERIA = {
    "type": "criteria",
    "op": "and",
    "criteria": [
        {"type": "word", "word": "murder"},
        {
            "type": "criteria",
            "op": "or",
            "criteria": [
                {"type": "character", "character": "Karakas"},
                {"type": "character", "character": "Arthurton"},
            ],
        },
    ],
}


async def main() -> None:
    async with streamable_http_client(
        mcp_url,
        headers={"Authorization": f"Bearer {token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool(
                "find_paragraphs",
                {"document_id": document_id, "criteria": CRITERIA},
            )
            print(json.dumps(json.loads(result.content[0].text), indent=2))


asyncio.run(main())
EOF

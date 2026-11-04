curl -s -X POST http://127.0.0.1:8000/api/mcp/mint \
     -H "X-MCP-Mint-Secret: $DOCKB_SECRET_KEY" \
     -H "Content-Type: application/json" \
     -d '{"prompt_id": "prompt-1", "account_id": "ac0bb3e8-ff1f-46a8-ab2e-1b89649600a8"}'

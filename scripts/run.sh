#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/run"
NEO4J_DATADIR="$HOME/Library/Application Support/neo4j-desktop/Application/Data/dbmss"

cd "$PROJECT_ROOT"

# --- Create run/ directory ---
mkdir -p "$RUN_DIR"

# --- Idempotent git init for snapshots ---
cd "$RUN_DIR"
if [ ! -d ".git" ]; then
    git init
    git add .
    git commit -m "Initial commit" --allow-empty
    echo "Snapshot repository created in run/"
else
    echo "Snapshot repository already exists."
fi

# --- Ensure Neo4j is running ---
echo "Checking Neo4j..."

neo4j_ready() {
    nc -z localhost 7687 2>/dev/null
}

if neo4j_ready; then
    echo "Neo4j is already running."
else
    echo "Neo4j is not running. Locating neo4j binary..."
    shopt -s nullglob
    bins=( "$NEO4J_DATADIR"/*/bin/neo4j )
    shopt -u nullglob
    if [ ${#bins[@]} -eq 0 ]; then
        echo "ERROR: No neo4j binary found under $NEO4J_DATADIR" >&2
        exit 1
    fi
    NEO4J_BIN="${bins[0]}"
    echo "Starting Neo4j via: $NEO4J_BIN"
    "$NEO4J_BIN" start
    for i in $(seq 1 30); do
        if neo4j_ready; then
            echo "Neo4j is ready."
            break
        fi
        sleep 1
    done
    if ! neo4j_ready; then
        echo "ERROR: Neo4j did not become ready within 30 seconds." >&2
        exit 1
    fi
fi

# --- Start the backend ---
cd "$PROJECT_ROOT/src"
exec ../.venv/bin/python3 -m main

#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/run"
find_neo4j_conf() {
    local default="/etc/neo4j/neo4j.conf"
    if [[ -f "$default" ]]; then
        echo "$default"
        return
    fi
    local found
    found=$(find / -name neo4j.conf -type f 2>/dev/null | head -n1)
    if [[ -n "$found" ]]; then
        echo "$found"
    else
        echo "" >&2
    fi
}

get_neo4j_data_dir() {
    local conf="$1"
    local dir
    dir=$(grep -oP '^\s*server\.directories\.data\s*=\s*\K.*' "$conf" | head -n1 | xargs)
    echo "$dir"
}

if [[ "$OSTYPE" == darwin* ]]; then
    NEO4J_DATADIR="$HOME/Library/Application Support/neo4j-desktop/Application/Data/dbmss"
    start_neo4j() {
        shopt -s nullglob
        local bins=( "$NEO4J_DATADIR"/*/bin/neo4j )
        shopt -u nullglob
        if [[ ${#bins[@]} -eq 0 ]]; then
            echo "ERROR: No neo4j binary found under $NEO4J_DATADIR" >&2
            return 1
        fi
        local NEO4J_BIN="${bins[0]}"
        echo "Starting Neo4j via: $NEO4J_BIN"
        "$NEO4J_BIN" start
    }
elif [[ "$OSTYPE" == linux* ]]; then
    NEO4J_CONF=$(find_neo4j_conf)
    if [[ -z "$NEO4J_CONF" ]]; then
        echo "ERROR: Could not find neo4j.conf" >&2
        exit 1
    fi
    echo "Found neo4j.conf at: $NEO4J_CONF"
    NEO4J_DATADIR=$(get_neo4j_data_dir "$NEO4J_CONF")
    if [[ -z "$NEO4J_DATADIR" ]]; then
        echo "ERROR: server.directories.data not set in $NEO4J_CONF" >&2
        exit 1
    fi
    echo "Neo4j data directory: $NEO4J_DATADIR"
    start_neo4j() {
        if neo4j status 2>/dev/null | grep -q "Neo4j is running at pid"; then
            echo "Neo4j is already running."
            return
        fi
        echo "Starting Neo4j via systemctl..."
        sudo systemctl start neo4j
    }
else
    echo "ERROR: Unsupported OS: $OSTYPE" >&2
    exit 1
fi

cd "$PROJECT_ROOT"

# --- Create run/ directory ---
mkdir -p "$RUN_DIR"

# --- Idempotent git init for snapshots ---
cd "$RUN_DIR"
if [ ! -d ".git" ]; then
    git init
    git config commit.gpgsign false
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
    echo "Neo4j is not running."
    start_neo4j
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

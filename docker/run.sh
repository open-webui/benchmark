#!/bin/bash
# Run Open WebUI for benchmarking with a specific compute profile

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env file if present
if [ -f "$BENCHMARK_DIR/.env" ]; then
    set -a
    source "$BENCHMARK_DIR/.env"
    set +a
fi

# Default profile values (matches "default" compute profile)
CPU_LIMIT="${CPU_LIMIT:-2.0}"
MEMORY_LIMIT="${MEMORY_LIMIT:-8g}"
CPU_RESERVATION="${CPU_RESERVATION:-1.0}"
MEMORY_RESERVATION="${MEMORY_RESERVATION:-4g}"
OPEN_WEBUI_PORT="${OPEN_WEBUI_PORT:-8080}"

# Parse arguments
PROFILE="${1:-default}"

case "$PROFILE" in
  default)
    CPU_LIMIT="2.0"
    MEMORY_LIMIT="8g"
    CPU_RESERVATION="1.0"
    MEMORY_RESERVATION="4g"
    ;;
  minimal)
    CPU_LIMIT="1.0"
    MEMORY_LIMIT="4g"
    CPU_RESERVATION="0.5"
    MEMORY_RESERVATION="2g"
    ;;
  cloud_small)
    CPU_LIMIT="2.0"
    MEMORY_LIMIT="4g"
    CPU_RESERVATION="1.0"
    MEMORY_RESERVATION="2g"
    ;;
  cloud_medium)
    CPU_LIMIT="4.0"
    MEMORY_LIMIT="8g"
    CPU_RESERVATION="2.0"
    MEMORY_RESERVATION="4g"
    ;;
  cloud_large)
    CPU_LIMIT="8.0"
    MEMORY_LIMIT="16g"
    CPU_RESERVATION="4.0"
    MEMORY_RESERVATION="8g"
    ;;
  *)
    echo "Unknown profile: $PROFILE"
    echo "Available profiles: default, minimal, cloud_small, cloud_medium, cloud_large"
    exit 1
    ;;
esac

echo "Starting Open WebUI with profile: $PROFILE"
echo "  CPU Limit: $CPU_LIMIT"
echo "  Memory Limit: $MEMORY_LIMIT"
echo "  Port: $OPEN_WEBUI_PORT"
echo "  Ollama Base URL: ${OLLAMA_BASE_URL:-not set}"
echo "  Channels Enabled: ${ENABLE_CHANNELS:-true}"

export CPU_LIMIT
export MEMORY_LIMIT
export CPU_RESERVATION
export MEMORY_RESERVATION
export OPEN_WEBUI_PORT
export OLLAMA_BASE_URL
export ENABLE_CHANNELS

cd "$SCRIPT_DIR"
docker compose -f docker-compose.benchmark.yaml up -d

echo ""
echo "Open WebUI started at http://localhost:$OPEN_WEBUI_PORT"
echo "To stop: docker compose -f docker-compose.benchmark.yaml down"

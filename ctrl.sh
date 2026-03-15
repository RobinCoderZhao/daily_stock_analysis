#!/usr/bin/env bash
#
# ctrl.sh — SaaS multi-tenant service control script
#
# Usage:
#   ./ctrl.sh start    Start service (background)
#   ./ctrl.sh stop     Stop service
#   ./ctrl.sh restart  Restart service
#   ./ctrl.sh status   Show service status
#   ./ctrl.sh logs     Tail latest logs
#   ./ctrl.sh -h       Show help
#

set -euo pipefail

# ============ Configuration ============
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${APP_DIR}/venv/bin/python"
SYSTEM_PYTHON="${PYTHON:-python3}"

# Use venv python if available, otherwise fallback to system python
if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="$SYSTEM_PYTHON"
fi

# Load .env for HOST/PORT config (with defaults)
if [[ -f "${APP_DIR}/.env" ]]; then
    # shellcheck disable=SC1091
    set -a
    source "${APP_DIR}/.env"
    set +a
fi

HOST="${WEBUI_HOST:-127.0.0.1}"
PORT="${WEBUI_PORT:-8018}"

CMD="${PYTHON} -m uvicorn api.app:create_app --factory --host ${HOST} --port ${PORT}"
PID_FILE="${APP_DIR}/.saas.pid"
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/saas_server.log"
# =======================================

_pid() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(<"$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    return 1
}

do_start() {
    if pid=$(_pid); then
        echo "⚠️  Service is already running (PID: $pid)"
        return 0
    fi

    mkdir -p "$LOG_DIR"

    echo "🚀 Starting SaaS service..."
    cd "$APP_DIR"
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # Wait 3 seconds to confirm process is alive
    sleep 3
    if kill -0 "$new_pid" 2>/dev/null; then
        echo "✅ Service started (PID: $new_pid)"
        echo "   Listen: ${HOST}:${PORT}"
        echo "   Log:    ${LOG_FILE}"
    else
        echo "❌ Service failed to start, check log: $LOG_FILE"
        tail -20 "$LOG_FILE" 2>/dev/null || true
        rm -f "$PID_FILE"
        return 1
    fi
}

do_stop() {
    local stopped=false

    # 1) Try stopping via PID file
    if pid=$(_pid); then
        echo "🛑 Stopping service (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        stopped=true
    fi
    rm -f "$PID_FILE"

    # 2) Fallback: kill any remaining uvicorn processes on our port
    local pids
    pids=$(pgrep -f "uvicorn.*${PORT}" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "🛑 Killing remaining processes: $pids"
        echo "$pids" | xargs kill 2>/dev/null || true
        stopped=true
    fi

    if [[ "$stopped" == "true" ]]; then
        # Wait up to 5 seconds for graceful exit
        for i in $(seq 1 5); do
            if ! pgrep -f "uvicorn.*${PORT}" >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        # Force kill if still alive
        pids=$(pgrep -f "uvicorn.*${PORT}" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  Process not responding, force killing..."
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
        echo "✅ Service stopped"
    else
        echo "ℹ️  Service is not running"
    fi
}

do_restart() {
    do_stop
    sleep 1
    do_start
}

do_status() {
    if pid=$(_pid); then
        echo "✅ Service is running (PID: $pid)"
        echo "   Listen: ${HOST}:${PORT}"
        echo "   Log:    ${LOG_FILE}"
        # Show health
        local health
        health=$(curl -s "http://${HOST}:${PORT}/api/health" 2>/dev/null || echo "unreachable")
        echo "   Health: $health"
    else
        echo "❌ Service is not running"
    fi
}

do_logs() {
    local lines="${2:-50}"
    if [[ -f "$LOG_FILE" ]]; then
        tail -"$lines" -f "$LOG_FILE"
    else
        echo "ℹ️  Log file not found: $LOG_FILE"
    fi
}

show_help() {
    cat <<EOF
SaaS Multi-Tenant Service Control Script

Usage: $0 <command>

Commands:
  start     Start the service (background)
  stop      Stop the service
  restart   Restart the service
  status    Show service status and health
  logs      Tail the latest logs (Ctrl+C to exit)
  -h        Show this help

Configuration:
  APP_DIR   $APP_DIR
  PID_FILE  $PID_FILE
  LOG_FILE  $LOG_FILE
  PYTHON    $PYTHON
  Command   $CMD

Environment (.env):
  WEBUI_HOST  Listen address (default: 127.0.0.1)
  WEBUI_PORT  Listen port (default: 8018)
EOF
}

case "${1:-}" in
    start)   do_start   ;;
    stop)    do_stop    ;;
    restart) do_restart ;;
    status)  do_status  ;;
    logs)    do_logs "$@" ;;
    -h|--help|help) show_help ;;
    *)
        echo "❌ Unknown command: ${1:-}"
        echo "   Use '$0 -h' for help"
        exit 1
        ;;
esac

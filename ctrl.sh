#!/usr/bin/env bash
#
# ctrl.sh — daily_stock_analysis 服务控制脚本
#
# Usage:
#   ./ctrl.sh start    启动服务（后台）
#   ./ctrl.sh stop     停止服务
#   ./ctrl.sh restart  重启服务
#   ./ctrl.sh -h       显示帮助
#

set -euo pipefail

# ============ 配置 ============
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${PYTHON:-python3}"
CMD="${PYTHON} main.py --webui"
PID_FILE="${APP_DIR}/.webui.pid"
LOG_FILE="${APP_DIR}/logs/webui.log"
# ==============================

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
        echo "⚠️  服务已在运行 (PID: $pid)"
        return 0
    fi

    mkdir -p "$(dirname "$LOG_FILE")"

    echo "🚀 正在启动服务..."
    cd "$APP_DIR"
    nohup $CMD >> "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    # 等待 2 秒确认进程存活
    sleep 2
    if kill -0 "$new_pid" 2>/dev/null; then
        echo "✅ 服务已启动 (PID: $new_pid)"
        echo "   日志: $LOG_FILE"
    else
        echo "❌ 服务启动失败，请查看日志: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

do_stop() {
    local stopped=false

    # 1) 尝试通过 PID 文件停止
    if pid=$(_pid); then
        echo "🛑 正在停止服务 (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        stopped=true
    fi
    rm -f "$PID_FILE"

    # 2) 兜底：通过进程名匹配查杀残留进程
    local pids
    pids=$(pgrep -f "python.*main\.py.*--webui" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "🛑 发现残留进程: $pids，正在停止..."
        echo "$pids" | xargs kill 2>/dev/null || true
        stopped=true
    fi

    if [[ "$stopped" == "true" ]]; then
        # 等待进程退出，最多 5 秒
        for i in $(seq 1 5); do
            if ! pgrep -f "python.*main\.py.*--webui" >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        # 仍未退出则强杀
        pids=$(pgrep -f "python.*main\.py.*--webui" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            echo "⚠️  进程未响应，强制终止..."
            echo "$pids" | xargs kill -9 2>/dev/null || true
        fi
        echo "✅ 服务已停止"
    else
        echo "ℹ️  服务未在运行"
    fi
}

do_restart() {
    do_stop
    do_start
}

show_help() {
    cat <<EOF
daily_stock_analysis 服务控制脚本

用法: $0 <命令>

命令:
  start     后台启动 WebUI 服务
  stop      停止服务
  restart   重启服务
  -h        显示此帮助信息

配置:
  APP_DIR   $APP_DIR
  PID_FILE  $PID_FILE
  LOG_FILE  $LOG_FILE
  命令      $CMD

环境变量:
  PYTHON    Python 解释器路径 (默认: python3)
EOF
}

case "${1:-}" in
    start)   do_start   ;;
    stop)    do_stop    ;;
    restart) do_restart ;;
    -h|--help|help) show_help ;;
    *)
        echo "❌ 未知命令: ${1:-}"
        echo "   使用 '$0 -h' 查看帮助"
        exit 1
        ;;
esac

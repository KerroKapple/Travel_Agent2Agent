#!/bin/bash
# ============================================================
# SmartVoyage 服务启动脚本
# scripts/start_services.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 日志目录
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# PID文件目录
PID_DIR="$PROJECT_ROOT/.pids"
mkdir -p "$PID_DIR"

echo "============================================================"
echo "  SmartVoyage 服务启动脚本"
echo "============================================================"
echo "项目目录: $PROJECT_ROOT"
echo "日志目录: $LOG_DIR"
echo "============================================================"

# 检查 uv 环境（本项目统一使用 uv 管理 Python）
check_uv() {
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}错误: 未找到 uv，请先安装 https://docs.astral.sh/uv/${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ uv 已安装${NC}"
}

# 同步依赖
check_dependencies() {
    echo "同步依赖 (uv sync)..."
    uv sync --quiet || {
        echo -e "${RED}错误: uv sync 失败${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ 依赖就绪${NC}"
}

# 启动MCP服务
start_mcp_services() {
    echo ""
    echo "启动MCP服务..."
    
    # Weather MCP
    echo -n "  启动 Weather MCP (8000)... "
    uv run python -m src.mcp_servers.weather_mcp > "$LOG_DIR/weather_mcp.log" 2>&1 &
    echo $! > "$PID_DIR/weather_mcp.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
    
    # Ticket MCP
    echo -n "  启动 Ticket MCP (8001)... "
    uv run python -m src.mcp_servers.ticket_mcp > "$LOG_DIR/ticket_mcp.log" 2>&1 &
    echo $! > "$PID_DIR/ticket_mcp.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
    
    # Order MCP
    echo -n "  启动 Order MCP (8002)... "
    uv run python -m src.mcp_servers.order_mcp > "$LOG_DIR/order_mcp.log" 2>&1 &
    echo $! > "$PID_DIR/order_mcp.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
}

# 启动Agent服务
start_agent_services() {
    echo ""
    echo "启动Agent服务..."
    
    # Weather Agent
    echo -n "  启动 Weather Agent (5005)... "
    uv run python -m src.agents.weather_agent > "$LOG_DIR/weather_agent.log" 2>&1 &
    echo $! > "$PID_DIR/weather_agent.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
    
    # Ticket Agent
    echo -n "  启动 Ticket Agent (5006)... "
    uv run python -m src.agents.ticket_agent > "$LOG_DIR/ticket_agent.log" 2>&1 &
    echo $! > "$PID_DIR/ticket_agent.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
    
    # Order Agent
    echo -n "  启动 Order Agent (5007)... "
    uv run python -m src.agents.order_agent > "$LOG_DIR/order_agent.log" 2>&1 &
    echo $! > "$PID_DIR/order_agent.pid"
    sleep 1
    echo -e "${GREEN}✓${NC}"
}

# 启动Web应用
start_web() {
    echo ""
    echo "启动Web应用..."
    echo -n "  启动 Streamlit (8501)... "
    uv run streamlit run src/app.py --server.port=8501 --server.address=0.0.0.0 > "$LOG_DIR/streamlit.log" 2>&1 &
    echo $! > "$PID_DIR/streamlit.pid"
    sleep 2
    echo -e "${GREEN}✓${NC}"
}

# 显示服务状态
show_status() {
    echo ""
    echo "============================================================"
    echo "  服务状态"
    echo "============================================================"
    echo "  MCP服务:"
    echo "    - Weather MCP:  http://localhost:8000"
    echo "    - Ticket MCP:   http://localhost:8001"
    echo "    - Order MCP:    http://localhost:8002"
    echo ""
    echo "  Agent服务:"
    echo "    - Weather Agent: http://localhost:5005"
    echo "    - Ticket Agent:  http://localhost:5006"
    echo "    - Order Agent:   http://localhost:5007"
    echo ""
    echo "  Web应用:"
    echo "    - Streamlit:     http://localhost:8501"
    echo "============================================================"
    echo ""
    echo -e "${GREEN}所有服务已启动！${NC}"
    echo "查看日志: tail -f $LOG_DIR/*.log"
}

# 停止所有服务
stop_all() {
    echo "停止所有服务..."
    for pid_file in "$PID_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "  已停止 PID: $pid"
            fi
            rm "$pid_file"
        fi
    done
    echo -e "${GREEN}所有服务已停止${NC}"
}

# 主函数
main() {
    case "${1:-start}" in
        start)
            check_uv
            check_dependencies
            start_mcp_services
            start_agent_services
            start_web
            show_status
            ;;
        stop)
            stop_all
            ;;
        restart)
            stop_all
            sleep 2
            main start
            ;;
        status)
            show_status
            ;;
        *)
            echo "用法: $0 {start|stop|restart|status}"
            exit 1
            ;;
    esac
}

main "$@"

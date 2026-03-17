#!/bin/bash

# AcademiaGPT-V2 一键启动脚本
# 使用方法: ./start.sh [--backend-only | --frontend-only]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# 日志目录
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# PID 文件
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
LANGGRAPH_PID_FILE="$LOG_DIR/langgraph.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

# 打印带颜色的消息
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 未安装，请先安装"
        return 1
    fi
    return 0
}

# 检查服务是否运行
is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# 等待服务启动
wait_for_service() {
    local url="$1"
    local name="$2"
    local max_attempts=30
    local attempt=0

    log_info "等待 $name 启动..."
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            log_success "$name 已就绪"
            return 0
        fi
        sleep 1
        ((attempt++))
    done
    log_error "$name 启动超时"
    return 1
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    local missing=0

    # 检查 Python/uv
    if ! check_command uv; then
        if ! check_command python3; then
            missing=1
        fi
    fi

    # 检查 Node.js
    if ! check_command node; then
        missing=1
    fi

    # 检查 npm
    if ! check_command npm; then
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        log_error "缺少必要依赖，请先安装"
        exit 1
    fi

    log_success "依赖检查通过"
}

# 检查 PostgreSQL
check_postgres() {
    log_info "检查 PostgreSQL..."

    # 默认连接信息
    DB_HOST="localhost"
    DB_PORT="5432"
    DB_USER="postgres"
    DB_PASS="postgres"
    DB_NAME="academiagpt"

    # 从 .env 读取数据库配置
    if [ -f "$BACKEND_DIR/.env" ]; then
        # 解析 DATABASE_URL
        local db_url=$(grep -v '^#' "$BACKEND_DIR/.env" | grep DATABASE_URL | head -1 | cut -d'=' -f2-)
        if [ -n "$db_url" ]; then
            # 提取用户名和密码 postgresql+asyncpg://user:pass@host:port/db
            DB_USER=$(echo "$db_url" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
            DB_PASS=$(echo "$db_url" | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
            DB_HOST=$(echo "$db_url" | sed -n 's/.*@\([^:]*\):.*/\1/p')
            DB_PORT=$(echo "$db_url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
            DB_NAME=$(echo "$db_url" | sed -n 's/.*\/\([^?]*\).*/\1/p')
        fi
    fi

    if command -v psql &> /dev/null; then
        # 使用 PGPASSWORD 环境变量避免密码提示
        if PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
            log_success "PostgreSQL 连接正常"
            return 0
        else
            log_warn "PostgreSQL 连接失败，请确保数据库服务正在运行"
            log_warn "数据库: $DB_HOST:$DB_PORT/$DB_NAME (用户: $DB_USER)"
            log_warn "如果使用 Docker: docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg16"
            return 1
        fi
    else
        log_warn "psql 未安装，跳过数据库连接检查"
        return 0
    fi
}

# 初始化后端环境
init_backend() {
    log_info "初始化后端环境..."

    cd "$BACKEND_DIR"

    # 检查 .env 文件
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            log_warn ".env 文件不存在，从 .env.example 复制..."
            cp .env.example .env
            log_warn "请编辑 backend/.env 文件，填入你的 API 密钥"
        else
            log_error ".env.example 文件不存在"
            exit 1
        fi
    fi

    # 安装依赖
    if check_command uv; then
        log_info "使用 uv 安装依赖..."
        uv sync
    else
        log_info "使用 pip 安装依赖..."
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt 2>/dev/null || pip install -e .
    fi

    # 运行数据库迁移
    log_info "运行数据库迁移..."
    if check_command uv; then
        uv run alembic upgrade head 2>/dev/null || log_warn "数据库迁移跳过（可能已完成）"
    else
        source .venv/bin/activate
        alembic upgrade head 2>/dev/null || log_warn "数据库迁移跳过（可能已完成）"
    fi

    log_success "后端环境初始化完成"
}

# 初始化前端环境
init_frontend() {
    log_info "初始化前端环境..."

    cd "$FRONTEND_DIR"

    # 检查 .env.local 文件
    if [ ! -f ".env.local" ]; then
        if [ -f ".env.example" ]; then
            log_warn ".env.local 文件不存在，从 .env.example 复制..."
            cp .env.example .env.local
        elif [ -f ".env.local.example" ]; then
            log_warn ".env.local 文件不存在，从 .env.local.example 复制..."
            cp .env.local.example .env.local
        fi
    fi

    # 安装依赖
    log_info "安装 npm 依赖..."
    npm install

    log_success "前端环境初始化完成"
}

# 启动 LangGraph 服务
start_langgraph() {
    if is_running "$LANGGRAPH_PID_FILE"; then
        log_warn "LangGraph 服务已在运行中 (PID: $(cat $LANGGRAPH_PID_FILE))"
        return 0
    fi

    # LangGraph CLI 需要 Docker
    if ! command -v docker &> /dev/null; then
        log_warn "LangGraph 服务需要 Docker，跳过启动"
        log_warn "如需完整功能，请安装 Docker 后运行: docker-compose up -d"
        return 0
    fi

    log_info "启动 LangGraph 服务..."

    cd "$BACKEND_DIR"

    # 使用 langgraph up 命令启动（需要 Docker）
    nohup uv run langgraph up --port 2024 > "$LOG_DIR/langgraph.log" 2>&1 &
    echo $! > "$LANGGRAPH_PID_FILE"

    sleep 5

    if is_running "$LANGGRAPH_PID_FILE"; then
        log_success "LangGraph 服务已启动 (PID: $(cat $LANGGRAPH_PID_FILE))"
        log_info "LangGraph 地址: http://localhost:2024"
    else
        log_warn "LangGraph 服务启动失败，查看日志: $LOG_DIR/langgraph.log"
        return 1
    fi
}

# 启动后端
start_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        log_warn "后端服务已在运行中 (PID: $(cat $BACKEND_PID_FILE))"
        return 0
    fi

    log_info "启动后端服务..."

    cd "$BACKEND_DIR"

    if check_command uv; then
        # 启动 Gateway
        uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 --reload > "$LOG_DIR/backend.log" 2>&1 &
        echo $! > "$BACKEND_PID_FILE"
    else
        source .venv/bin/activate
        uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 --reload > "$LOG_DIR/backend.log" 2>&1 &
        echo $! > "$BACKEND_PID_FILE"
    fi

    sleep 2

    if is_running "$BACKEND_PID_FILE"; then
        log_success "后端服务已启动 (PID: $(cat $BACKEND_PID_FILE))"
        log_info "后端地址: http://localhost:8001"
        log_info "API 文档: http://localhost:8001/docs"
    else
        log_error "后端服务启动失败，查看日志: $LOG_DIR/backend.log"
        return 1
    fi
}

# 启动前端
start_frontend() {
    if is_running "$FRONTEND_PID_FILE"; then
        log_warn "前端服务已在运行中 (PID: $(cat $FRONTEND_PID_FILE))"
        return 0
    fi

    log_info "启动前端服务..."

    cd "$FRONTEND_DIR"

    npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"

    sleep 3

    if is_running "$FRONTEND_PID_FILE"; then
        log_success "前端服务已启动 (PID: $(cat $FRONTEND_PID_FILE))"
        log_info "前端地址: http://localhost:3000"
    else
        log_error "前端服务启动失败，查看日志: $LOG_DIR/frontend.log"
        return 1
    fi
}

# 停止服务
stop_services() {
    log_info "停止所有服务..."

    for pid_file in "$BACKEND_PID_FILE" "$LANGGRAPH_PID_FILE" "$FRONTEND_PID_FILE"; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if ps -p "$pid" > /dev/null 2>&1; then
                kill "$pid" 2>/dev/null || true
                log_info "已停止进程 $pid"
            fi
            rm -f "$pid_file"
        fi
    done

    # 额外清理可能残留的进程
    pkill -f "uvicorn src.gateway" 2>/dev/null || true
    pkill -f "langgraph api" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true

    log_success "所有服务已停止"
}

# 显示状态
show_status() {
    echo ""
    echo "======================================"
    echo "         AcademiaGPT-V2 状态"
    echo "======================================"

    if is_running "$BACKEND_PID_FILE"; then
        echo -e "后端服务:   ${GREEN}运行中${NC} (PID: $(cat $BACKEND_PID_FILE))"
        echo "           http://localhost:8001"
    else
        echo -e "后端服务:   ${RED}未运行${NC}"
    fi

    if is_running "$LANGGRAPH_PID_FILE"; then
        echo -e "LangGraph:  ${GREEN}运行中${NC} (PID: $(cat $LANGGRAPH_PID_FILE))"
        echo "           http://localhost:2024"
    else
        echo -e "LangGraph:  ${YELLOW}未运行${NC}"
    fi

    if is_running "$FRONTEND_PID_FILE"; then
        echo -e "前端服务:   ${GREEN}运行中${NC} (PID: $(cat $FRONTEND_PID_FILE))"
        echo "           http://localhost:3000"
    else
        echo -e "前端服务:   ${RED}未运行${NC}"
    fi

    echo ""
    echo "日志目录: $LOG_DIR"
    echo "======================================"
}

# 显示帮助
show_help() {
    echo "AcademiaGPT-V2 启动脚本"
    echo ""
    echo "使用方法:"
    echo "  ./start.sh              # 启动所有服务"
    echo "  ./start.sh --init       # 仅初始化环境（不启动服务）"
    echo "  ./start.sh --backend    # 仅启动后端"
    echo "  ./start.sh --langgraph  # 仅启动 LangGraph"
    echo "  ./start.sh --frontend   # 仅启动前端"
    echo "  ./start.sh --stop       # 停止所有服务"
    echo "  ./start.sh --status     # 查看服务状态"
    echo "  ./start.sh --logs       # 查看日志"
    echo "  ./start.sh --help       # 显示帮助"
}

# 查看日志
show_logs() {
    local service="$1"
    case "$service" in
        backend)
            tail -f "$LOG_DIR/backend.log"
            ;;
        frontend)
            tail -f "$LOG_DIR/frontend.log"
            ;;
        langgraph)
            tail -f "$LOG_DIR/langgraph.log"
            ;;
        *)
            echo "可用日志: backend, frontend, langgraph"
            ;;
    esac
}

# 主函数
main() {
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --stop)
            stop_services
            exit 0
            ;;
        --status)
            show_status
            exit 0
            ;;
        --logs)
            show_logs "${2:-}"
            exit 0
            ;;
        --init)
            check_dependencies
            init_backend
            init_frontend
            log_success "环境初始化完成"
            exit 0
            ;;
    esac

    # 检查依赖
    check_dependencies

    # 检查 PostgreSQL
    check_postgres || true

    case "${1:-}" in
        --backend)
            init_backend
            start_backend
            ;;
        --langgraph)
            init_backend
            start_langgraph
            ;;
        --frontend)
            init_frontend
            start_frontend
            ;;
        *)
            # 启动所有服务
            init_backend
            init_frontend
            start_backend
            start_langgraph || true
            start_frontend
            ;;
    esac

    show_status

    echo ""
    log_success "启动完成！按 Ctrl+C 停止所有服务"

    # 捕获退出信号
    trap stop_services EXIT INT TERM

    # 保持脚本运行
    wait
}

main "$@"

#!/bin/bash

# 观澜 Guanlan 一键启动脚本
# 使用方法: ./start.sh [--backend-only | --frontend-only]

set -e
set -o pipefail

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
ENSURE_TEXLIVE_SCRIPT="$PROJECT_ROOT/scripts/ensure_texlive_image.sh"

# 本地兜底容器（当宿主机 PostgreSQL/Redis 不满足要求时）
LOCAL_PGVECTOR_CONTAINER="${LOCAL_PGVECTOR_CONTAINER:-guanlan-local-postgres}"
LOCAL_REDIS_CONTAINER="${LOCAL_REDIS_CONTAINER:-guanlan-local-redis}"
LOCAL_PGVECTOR_PORT="${LOCAL_PGVECTOR_PORT:-55432}"
LOCAL_REDIS_PORT="${LOCAL_REDIS_PORT:-56379}"

# 运行时连接（可被自动兜底覆盖）
RUNTIME_DATABASE_URL=""
RUNTIME_REDIS_URL=""
RUNTIME_DATABASE_URL_OVERRIDE=""
RUNTIME_REDIS_URL_OVERRIDE=""
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="postgres"
DB_PASS="postgres"
DB_NAME="academiagpt"
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_DB="0"

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

# 从 backend/.env 读取运行时连接配置
load_runtime_config() {
    RUNTIME_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/academiagpt"
    RUNTIME_REDIS_URL="redis://localhost:6379/0"

    DB_HOST="localhost"
    DB_PORT="5432"
    DB_USER="postgres"
    DB_PASS="postgres"
    DB_NAME="academiagpt"

    REDIS_HOST="localhost"
    REDIS_PORT="6379"
    REDIS_DB="0"

    if [ -f "$BACKEND_DIR/.env" ]; then
        local db_url
        db_url=$(grep -v '^#' "$BACKEND_DIR/.env" | grep '^DATABASE_URL=' | head -1 | cut -d'=' -f2- || true)
        local redis_url
        redis_url=$(grep -v '^#' "$BACKEND_DIR/.env" | grep '^REDIS_URL=' | head -1 | cut -d'=' -f2- || true)

        if [ -n "$db_url" ]; then
            RUNTIME_DATABASE_URL="$db_url"
            DB_USER=$(echo "$db_url" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
            DB_PASS=$(echo "$db_url" | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
            DB_HOST=$(echo "$db_url" | sed -n 's/.*@\([^:\/]*\):.*/\1/p')
            DB_PORT=$(echo "$db_url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
            DB_NAME=$(echo "$db_url" | sed -n 's#.*/\([^?]*\).*#\1#p')
        fi

        if [ -n "$redis_url" ]; then
            RUNTIME_REDIS_URL="$redis_url"
            REDIS_HOST=$(echo "$redis_url" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\1#p')
            REDIS_PORT=$(echo "$redis_url" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\2#p')
            REDIS_DB=$(echo "$redis_url" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\3#p')
            REDIS_HOST=${REDIS_HOST:-localhost}
            REDIS_PORT=${REDIS_PORT:-6379}
            REDIS_DB=${REDIS_DB:-0}
        fi
    fi

    if [ -n "$RUNTIME_DATABASE_URL_OVERRIDE" ]; then
        RUNTIME_DATABASE_URL="$RUNTIME_DATABASE_URL_OVERRIDE"
        DB_USER=$(echo "$RUNTIME_DATABASE_URL" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
        DB_PASS=$(echo "$RUNTIME_DATABASE_URL" | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
        DB_HOST=$(echo "$RUNTIME_DATABASE_URL" | sed -n 's/.*@\([^:\/]*\):.*/\1/p')
        DB_PORT=$(echo "$RUNTIME_DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        DB_NAME=$(echo "$RUNTIME_DATABASE_URL" | sed -n 's#.*/\([^?]*\).*#\1#p')
    fi

    if [ -n "$RUNTIME_REDIS_URL_OVERRIDE" ]; then
        RUNTIME_REDIS_URL="$RUNTIME_REDIS_URL_OVERRIDE"
        REDIS_HOST=$(echo "$RUNTIME_REDIS_URL" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\1#p')
        REDIS_PORT=$(echo "$RUNTIME_REDIS_URL" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\2#p')
        REDIS_DB=$(echo "$RUNTIME_REDIS_URL" | sed -n 's#redis://\([^:/]*\):\([0-9]*\)/\([0-9]*\).*#\3#p')
        REDIS_HOST=${REDIS_HOST:-localhost}
        REDIS_PORT=${REDIS_PORT:-6379}
        REDIS_DB=${REDIS_DB:-0}
    fi
}

postgres_can_connect() {
    if ! command -v psql &> /dev/null; then
        return 1
    fi
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1
}

postgres_supports_vector() {
    if ! command -v psql &> /dev/null; then
        return 1
    fi
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
        "SELECT 1 FROM pg_available_extensions WHERE name='vector';" | grep -q "1"
}

postgres_enable_vector() {
    if ! command -v psql &> /dev/null; then
        return 1
    fi
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null 2>&1
}

redis_can_connect() {
    if command -v redis-cli &> /dev/null; then
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -n "$REDIS_DB" ping 2>/dev/null | grep -q "PONG"
        return $?
    fi
    (echo > "/dev/tcp/$REDIS_HOST/$REDIS_PORT") > /dev/null 2>&1
}

ensure_local_pgvector_container() {
    if ! command -v docker &> /dev/null; then
        log_error "本机 PostgreSQL 不满足 pgvector 要求，且 Docker 不可用，无法自动兜底"
        return 1
    fi

    log_warn "检测到当前数据库不支持 pgvector，尝试启动本地 pgvector 容器兜底..."

    if docker ps -a --format '{{.Names}}' | grep -Fx "$LOCAL_PGVECTOR_CONTAINER" > /dev/null; then
        docker start "$LOCAL_PGVECTOR_CONTAINER" > /dev/null || true
    else
        docker run -d \
            --name "$LOCAL_PGVECTOR_CONTAINER" \
            --restart unless-stopped \
            -p "${LOCAL_PGVECTOR_PORT}:5432" \
            -e POSTGRES_USER=postgres \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=academiagpt \
            pgvector/pgvector:pg16 > /dev/null
    fi

    local attempts=0
    while [ $attempts -lt 30 ]; do
        if PGPASSWORD="postgres" psql -h "localhost" -p "$LOCAL_PGVECTOR_PORT" -U "postgres" -d "academiagpt" -c "SELECT 1" > /dev/null 2>&1; then
            break
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    if [ $attempts -ge 30 ]; then
        log_error "本地 pgvector 容器启动超时（${LOCAL_PGVECTOR_CONTAINER}）"
        return 1
    fi

    DB_HOST="localhost"
    DB_PORT="$LOCAL_PGVECTOR_PORT"
    DB_USER="postgres"
    DB_PASS="postgres"
    DB_NAME="academiagpt"
    RUNTIME_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:${LOCAL_PGVECTOR_PORT}/academiagpt"
    RUNTIME_DATABASE_URL_OVERRIDE="$RUNTIME_DATABASE_URL"

    if ! postgres_enable_vector; then
        log_error "本地 pgvector 容器已启动，但创建 vector 扩展失败"
        return 1
    fi

    log_success "已切换到本地 pgvector 数据库: $DB_HOST:$DB_PORT/$DB_NAME"
    return 0
}

ensure_local_redis_container() {
    if ! command -v docker &> /dev/null; then
        log_error "Redis 不可用，且 Docker 不可用，无法自动兜底"
        return 1
    fi

    log_warn "检测到 Redis 不可用，尝试启动本地 Redis 容器兜底..."

    if docker ps -a --format '{{.Names}}' | grep -Fx "$LOCAL_REDIS_CONTAINER" > /dev/null; then
        docker start "$LOCAL_REDIS_CONTAINER" > /dev/null || true
    else
        docker run -d \
            --name "$LOCAL_REDIS_CONTAINER" \
            --restart unless-stopped \
            -p "${LOCAL_REDIS_PORT}:6379" \
            redis:7-alpine > /dev/null
    fi

    local attempts=0
    while [ $attempts -lt 30 ]; do
        if command -v redis-cli &> /dev/null; then
            if redis-cli -h "localhost" -p "$LOCAL_REDIS_PORT" ping 2>/dev/null | grep -q "PONG"; then
                break
            fi
        elif (echo > "/dev/tcp/localhost/$LOCAL_REDIS_PORT") > /dev/null 2>&1; then
            break
        fi
        sleep 1
        attempts=$((attempts + 1))
    done

    if [ $attempts -ge 30 ]; then
        log_error "本地 Redis 容器启动超时（${LOCAL_REDIS_CONTAINER}）"
        return 1
    fi

    REDIS_HOST="localhost"
    REDIS_PORT="$LOCAL_REDIS_PORT"
    REDIS_DB="0"
    RUNTIME_REDIS_URL="redis://localhost:${LOCAL_REDIS_PORT}/0"
    RUNTIME_REDIS_URL_OVERRIDE="$RUNTIME_REDIS_URL"
    log_success "已切换到本地 Redis: $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
    return 0
}

# 自动准备 LaTeX Docker 镜像（用于论文编译执行）
ensure_texlive_image() {
    if [ "${SKIP_TEXLIVE_IMAGE_ENSURE:-0}" = "1" ]; then
        log_warn "已跳过 TeXLive 镜像准备（SKIP_TEXLIVE_IMAGE_ENSURE=1）"
        return 0
    fi

    if ! command -v docker &> /dev/null; then
        log_warn "Docker 未安装，跳过 TeXLive 镜像准备"
        return 0
    fi

    if [ ! -x "$ENSURE_TEXLIVE_SCRIPT" ]; then
        log_warn "未找到镜像准备脚本: $ENSURE_TEXLIVE_SCRIPT"
        return 0
    fi

    log_info "自动准备 TeXLive 镜像（academiagpt/texlive:2024）..."
    if "$ENSURE_TEXLIVE_SCRIPT"; then
        log_success "TeXLive 镜像就绪"
    else
        log_warn "TeXLive 镜像准备失败，LaTeX 编译功能可能不可用"
    fi
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
    local max_attempts=60
    local attempt=0

    log_info "等待 $name 启动..."
    while [ $attempt -lt $max_attempts ]; do
        if is_http_ready "$url"; then
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

    # 检查 PostgreSQL 客户端（用于健康检查与迁移前置验证）
    if ! check_command psql; then
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
    load_runtime_config

    if ! postgres_can_connect; then
        log_warn "PostgreSQL 连接失败: $DB_HOST:$DB_PORT/$DB_NAME (用户: $DB_USER)"
        if ! ensure_local_pgvector_container; then
            log_error "数据库不可用。请启动 PostgreSQL（并确保 pgvector 可用）后重试"
            return 1
        fi
    fi

    if ! postgres_supports_vector; then
        log_warn "当前 PostgreSQL 不支持 pgvector 扩展"
        if ! ensure_local_pgvector_container; then
            log_error "pgvector 扩展不可用，后端无法启动"
            return 1
        fi
    fi

    if ! postgres_enable_vector; then
        log_error "无法在目标数据库创建/确认 vector 扩展"
        return 1
    fi

    log_success "PostgreSQL 连接正常且 pgvector 可用: $DB_HOST:$DB_PORT/$DB_NAME"
    return 0
}

# 检查 Redis
check_redis() {
    log_info "检查 Redis..."

    if redis_can_connect; then
        log_success "Redis 连接正常: $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
        return 0
    fi

    log_warn "Redis 连接失败: $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
    if ! ensure_local_redis_container; then
        log_error "Redis 不可用，后端无法启动"
        return 1
    fi

    if redis_can_connect; then
        log_success "Redis 连接正常: $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
        return 0
    fi

    log_error "Redis 连接验证失败"
    return 1
}

is_http_ready() {
    local url="$1"
    curl --max-time 2 -fsS "$url" > /dev/null 2>&1
}

# 初始化后端环境
init_backend() {
    log_info "初始化后端环境..."

    cd "$BACKEND_DIR"
    load_runtime_config

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

    # 运行数据库迁移（兼容 legacy create_all 无 alembic_version 的历史库）
    log_info "运行数据库迁移..."
    if check_command uv; then
        if ! env DATABASE_URL="$RUNTIME_DATABASE_URL" REDIS_URL="$RUNTIME_REDIS_URL" uv run python -m src.database.migration_bootstrap; then
            log_error "数据库迁移失败，请检查配置与迁移链"
            return 1
        fi
    else
        source .venv/bin/activate
        if ! env DATABASE_URL="$RUNTIME_DATABASE_URL" REDIS_URL="$RUNTIME_REDIS_URL" python -m src.database.migration_bootstrap; then
            log_error "数据库迁移失败，请检查配置与迁移链"
            return 1
        fi
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

    # 安装依赖（优先使用 npm ci，避免无意改写 lockfile）
    log_info "安装 npm 依赖..."
    if [ -f "package-lock.json" ]; then
        npm ci
    else
        npm install
    fi

    log_success "前端环境初始化完成"
}

# 启动 LangGraph 服务
start_langgraph() {
    if is_running "$LANGGRAPH_PID_FILE"; then
        if is_http_ready "http://localhost:2024/info"; then
            log_warn "LangGraph 服务已在运行中 (PID: $(cat $LANGGRAPH_PID_FILE))"
            return 0
        fi
        log_warn "检测到 LangGraph 进程存在但健康检查失败，尝试重启..."
        rm -f "$LANGGRAPH_PID_FILE"
    fi

    # LangGraph CLI 需要 Docker
    if ! command -v docker &> /dev/null; then
        log_warn "LangGraph 服务需要 Docker，跳过启动"
        log_warn "如需完整功能，请安装 Docker 后运行: docker-compose up -d"
        return 0
    fi

    log_info "启动 LangGraph 服务..."

    cd "$BACKEND_DIR"
    load_runtime_config

    # 使用 langgraph dev 启动本地开发服务（避免 langgraph up 的部署构建阻塞）
    nohup env DATABASE_URL="$RUNTIME_DATABASE_URL" REDIS_URL="$RUNTIME_REDIS_URL" \
        uv run langgraph dev --no-browser --no-reload --host 0.0.0.0 --port 2024 --config langgraph.json \
        > "$LOG_DIR/langgraph.log" 2>&1 &
    echo $! > "$LANGGRAPH_PID_FILE"

    if is_running "$LANGGRAPH_PID_FILE" && wait_for_service "http://localhost:2024/info" "LangGraph"; then
        log_success "LangGraph 服务已启动 (PID: $(cat $LANGGRAPH_PID_FILE))"
        log_info "LangGraph 地址: http://localhost:2024"
    else
        log_error "LangGraph 服务启动失败，查看日志: $LOG_DIR/langgraph.log"
        rm -f "$LANGGRAPH_PID_FILE"
        tail -n 60 "$LOG_DIR/langgraph.log" || true
        return 1
    fi
}

# 启动后端
start_backend() {
    if is_running "$BACKEND_PID_FILE"; then
        if is_http_ready "http://localhost:8001/readyz"; then
            log_warn "后端服务已在运行中 (PID: $(cat $BACKEND_PID_FILE))"
            return 0
        fi
        log_warn "检测到后端进程存在但健康检查失败，尝试重启..."
        rm -f "$BACKEND_PID_FILE"
    fi

    log_info "启动后端服务..."

    cd "$BACKEND_DIR"
    load_runtime_config

    if check_command uv; then
        # 启动 Gateway
        env DATABASE_URL="$RUNTIME_DATABASE_URL" REDIS_URL="$RUNTIME_REDIS_URL" uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 > "$LOG_DIR/backend.log" 2>&1 &
        echo $! > "$BACKEND_PID_FILE"
    else
        source .venv/bin/activate
        env DATABASE_URL="$RUNTIME_DATABASE_URL" REDIS_URL="$RUNTIME_REDIS_URL" uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 > "$LOG_DIR/backend.log" 2>&1 &
        echo $! > "$BACKEND_PID_FILE"
    fi

    if is_running "$BACKEND_PID_FILE" && wait_for_service "http://localhost:8001/readyz" "后端服务"; then
        log_success "后端服务已启动 (PID: $(cat $BACKEND_PID_FILE))"
        log_info "后端地址: http://localhost:8001"
        log_info "API 文档: http://localhost:8001/docs"
    else
        log_error "后端服务启动失败，查看日志: $LOG_DIR/backend.log"
        rm -f "$BACKEND_PID_FILE"
        tail -n 80 "$LOG_DIR/backend.log" || true
        return 1
    fi
}

# 启动前端
start_frontend() {
    if is_running "$FRONTEND_PID_FILE"; then
        if is_http_ready "http://localhost:3000"; then
            log_warn "前端服务已在运行中 (PID: $(cat $FRONTEND_PID_FILE))"
            return 0
        fi
        log_warn "检测到前端进程存在但健康检查失败，尝试重启..."
        rm -f "$FRONTEND_PID_FILE"
    fi

    log_info "启动前端服务..."

    cd "$FRONTEND_DIR"

    npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"

    if is_running "$FRONTEND_PID_FILE" && wait_for_service "http://localhost:3000" "前端服务"; then
        log_success "前端服务已启动 (PID: $(cat $FRONTEND_PID_FILE))"
        log_info "前端地址: http://localhost:3000"
    else
        log_error "前端服务启动失败，查看日志: $LOG_DIR/frontend.log"
        rm -f "$FRONTEND_PID_FILE"
        tail -n 80 "$LOG_DIR/frontend.log" || true
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
    pkill -f "langgraph up" 2>/dev/null || true
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true

    log_success "所有服务已停止"
}

# 显示状态
show_status() {
    echo ""
    echo "======================================"
    echo "         观澜 Guanlan 状态"
    echo "======================================"

    if is_running "$BACKEND_PID_FILE" && is_http_ready "http://localhost:8001/readyz"; then
        echo -e "后端服务:   ${GREEN}运行中${NC} (PID: $(cat $BACKEND_PID_FILE))"
        echo "           http://localhost:8001"
    else
        echo -e "后端服务:   ${RED}未运行${NC}"
    fi

    if is_running "$LANGGRAPH_PID_FILE" && is_http_ready "http://localhost:2024/info"; then
        echo -e "LangGraph:  ${GREEN}运行中${NC} (PID: $(cat $LANGGRAPH_PID_FILE))"
        echo "           http://localhost:2024"
    else
        echo -e "LangGraph:  ${YELLOW}未运行${NC}"
    fi

    if is_running "$FRONTEND_PID_FILE" && is_http_ready "http://localhost:3000"; then
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
    echo "观澜 Guanlan 启动脚本"
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
    echo ""
    echo "环境变量:"
    echo "  SKIP_TEXLIVE_IMAGE_ENSURE=1  # 跳过自动准备 TeXLive 镜像"
    echo "  LOCAL_PGVECTOR_PORT=55432    # 本地 pgvector 兜底容器端口"
    echo "  LOCAL_REDIS_PORT=56379       # 本地 Redis 兜底容器端口"
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
            check_postgres
            check_redis
            init_backend
            init_frontend
            log_success "环境初始化完成"
            exit 0
            ;;
    esac

    # 检查依赖
    check_dependencies

    if [ "${1:-}" != "--frontend" ]; then
        # 检查 PostgreSQL 与 pgvector
        check_postgres
        # 检查 Redis
        check_redis
    fi

    case "${1:-}" in
        --backend)
            init_backend
            ensure_texlive_image
            start_backend
            ;;
        --langgraph)
            init_backend
            ensure_texlive_image
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
            ensure_texlive_image
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

#!/usr/bin/env bash
# ============================================================
# QB Network Graph — Entity Resolution Agent v3
# One-time setup: venv, deps, .env, validate, test
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Entity Resolution Agent v3 — Setup"
echo "══════════════════════════════════════════════════════"
echo ""

# 1. .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    info "Created .env from .env.example"
    warn "Edit .env with your API keys and MySQL credentials"
else
    info ".env already exists"
fi

# 2. Virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    info "Virtual environment created"
else
    info "Virtual environment already exists"
fi

source venv/bin/activate

# 3. Dependencies
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
info "Dependencies installed"

# 4. Validate imports
echo "Validating imports..."
python3 -c "import fastapi; print(f'  fastapi {fastapi.__version__}')"
python3 -c "import mysql.connector; print(f'  mysql-connector {mysql.connector.__version__}')"
python3 -c "import pymilvus; print(f'  pymilvus {pymilvus.__version__}')"
python3 -c "import google.generativeai; print(f'  google-generativeai OK')"
python3 -c "import rapidfuzz; print(f'  rapidfuzz {rapidfuzz.__version__}')"
info "All critical imports OK"

# 5. Run tests
echo ""
echo "Running tests..."
python3 -m pytest tests/ -v --tb=short || warn "Some tests failed (may need .env configured)"

echo ""
echo "══════════════════════════════════════════════════════"
info "Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your GEMINI_API_KEY (used for embeddings + LLM reasoning)"
echo "    2. Ensure MySQL is running (docker compose -f docker-compose-mysql.yml up -d)"
echo "    3. Ensure Milvus is running (docker compose -f docker-compose-milvus.yml up -d)"
echo "    4. Run: ./run.sh"
echo ""

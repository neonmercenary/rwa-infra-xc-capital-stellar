#!/usr/bin/env bash
# scripts/reset_and_run.sh

set -euo pipefail

# Colors for scannability
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== RWA PROJECT RESET & DEPLOYMENT ===${NC}"

# ------------------------------------------------------------------
# 1. Environment & Path Setup
# ------------------------------------------------------------------
if [[ ! -f manage.py ]]; then
  echo -e "${RED}✘ No manage.py found – run this from project root${NC}"
  exit 1
fi

# ------------------------------------------------------------------
# 2. Blockchain Artifacts (The Ape/Vyper Bypass)
# ------------------------------------------------------------------
# 1. Clean everything
echo -e "${GREEN}🧹 Cleaning old blockchain artifacts...${NC}"
rm -rf artifacts/*.abi artifacts/*.bin .build .ape

# 2. Compile RWALite
echo -e "${GREEN}🔨 Compiling RWALite...${NC}"
vyper -f abi contracts/RWALite.vy > artifacts/RWALite.abi
vyper -f bytecode contracts/RWALite.vy > artifacts/RWALite.bin

# 3. Compile RWATranch
echo -e "${GREEN}🔨 Compiling RWATranch...${NC}"
vyper -f abi contracts/RWATranch.vy > artifacts/RWATranch.abi
vyper -f bytecode contracts/RWATranch.vy > artifacts/RWATranch.bin

# 3. Compile RWATranchDemo
echo -e "${GREEN}🔨 Compiling RWATranchDemo...${NC}"
vyper -f abi contracts/RWATranchDemo.vy > artifacts/RWATranchDemo.abi
vyper -f bytecode contracts/RWATranchDemo.vy > artifacts/RWATranchDemo.bin


echo -e "${GREEN}✅ All artifacts generated independently.${NC}"

# Optional: Uncomment if you want to redeploy the Master Contract every reset
# echo -e "${GREEN}🚀 Deploying Master Contract to Fuji...${NC}"
# ape run deploy_script --network avalanche:fuji:alchemy

# ------------------------------------------------------------------
# 3. Database Cleanup
# ------------------------------------------------------------------
DB_FILE="${DB_FILE:-db.sqlite3}"
if [[ -f "$DB_FILE" ]]; then
  echo -e "${GREEN}♻ Removing old DB ($DB_FILE)${NC}"
  rm "$DB_FILE"
fi

echo -e "${GREEN}♻ Removing migrations and pycache...${NC}"
find . -type d -name migrations -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name __pycache__ -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true

# ------------------------------------------------------------------
# 4. Fresh Django Setup
# ------------------------------------------------------------------
echo -e "${GREEN}♻ Making migrations for 'app'...${NC}"
python manage.py makemigrations app

echo -e "${GREEN}♻ Applying migrations...${NC}"
python manage.py migrate --noinput

echo -e "${GREEN}♻ Seeding default TokenizationSpec...${NC}"
python manage.py create_default_spec

echo -e "${GREEN}♻ Seeding default Loans...${NC}"
python manage.py load_mock_loans
# ------------------------------------------------------------------
# 5. Super-user Creation
# ------------------------------------------------------------------
DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-neonalchemist}"
DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-spv@xeev.com}"
DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-heathens}"

echo -e "${GREEN}♻ Creating super-user: $DJANGO_SUPERUSER_USERNAME${NC}"
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
"

# ------------------------------------------------------------------
# 6. Start Server
# ------------------------------------------------------------------
echo -e "${BLUE}✅ Everything is ready! Starting dev server...${NC}"
echo -e "${BLUE}🔗 URL: http://127.0.0.1:8000/spv/dashboard/ ${NC}"
python manage.py runserver 0.0.0.0:8000
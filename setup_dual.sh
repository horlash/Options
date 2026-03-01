#!/bin/bash
set -e

# Source env vars from .env file if present
[ -f /root/.env ] && export $(grep -v '^#' /root/.env | xargs)

echo "=== Step 1: Restore prod compose ==="
cp /root/docker-compose.yml.bak /root/docker-compose.yml
echo "Prod compose restored"

echo "=== Step 2: Stop feature container if running ==="
docker stop leap_scanner_feature 2>/dev/null && docker rm leap_scanner_feature 2>/dev/null || true
docker stop paper_trading_db_dev 2>/dev/null && docker rm paper_trading_db_dev 2>/dev/null || true

echo "=== Step 3: Restart prod stack ==="
cd /root
docker compose down
docker compose up -d
echo "Waiting for prod DB healthy..."
sleep 15

echo "=== Step 4: Clone prod DB ==="
docker exec paper_trading_db pg_dump -U paper_user -d paper_trading > /root/prod_dump.sql
echo "Prod DB dumped"

echo "=== Step 5: Start dev PostgreSQL on port 5433 ==="
docker run -d \
  --name paper_trading_db_dev \
  --network root_default \
  -e POSTGRES_DB=paper_trading \
  -e POSTGRES_USER=paper_user \
  -e POSTGRES_PASSWORD=paper_pass \
  -p 5433:5432 \
  -v paper_pg_data_dev:/var/lib/postgresql/data \
  postgres:16-alpine

echo "Waiting for dev DB ready..."
sleep 10

echo "=== Step 6: Create app_user and restore dump ==="
docker exec paper_trading_db_dev psql -U paper_user -d paper_trading -c "
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_pass';
    END IF;
END
\$\$;
GRANT CONNECT ON DATABASE paper_trading TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO app_user;
"

docker exec -i paper_trading_db_dev psql -U paper_user -d paper_trading < /root/prod_dump.sql
echo "Dev DB loaded with prod data clone"

echo "=== Step 7: Start feature container on port 5001 ==="
docker run -d \
  --name leap_scanner_feature \
  --network root_default \
  -p 5001:5000 \
  -e PYTHONUNBUFFERED=1 \
  -e FLASK_APP=backend/app.py \
  -e FLASK_ENV=development \
  -e FLASK_DEBUG=True \
  -e PORT=5000 \
  -e SCHWAB_API_KEY="${SCHWAB_API_KEY}" \
  -e SCHWAB_API_SECRET="${SCHWAB_API_SECRET}" \
  -e FINNHUB_API_KEY="${FINNHUB_API_KEY}" \
  -e FMP_API_KEY="${FMP_API_KEY}" \
  -e SCHWAB_TOKEN_PATH=token.json \
  -e INTELLIGENCE_API_KEY="${INTELLIGENCE_API_KEY}" \
  -e PAPER_TRADE_DB_URL='postgresql://app_user:app_pass@paper_trading_db_dev:5432/paper_trading' \
  -e SECRET_KEY='dev-secret-key' \
  -e ORATS_API_KEY="${ORATS_API_KEY}" \
  -e PERPLEXITY_API_KEY="${PERPLEXITY_API_KEY}" \
  -e ENCRYPTION_KEY="${ENCRYPTION_KEY}" \
  -e ENABLE_VIX_REGIME=True \
  -e ENABLE_PUT_CALL_RATIO=True \
  -e ENABLE_RSI2=True \
  -e ENABLE_SECTOR_MOMENTUM=True \
  -e ENABLE_MINERVINI_FILTER=True \
  -e ENABLE_VWAP_LEVELS=True \
  horlamy/newscanner:feature-test

echo "Feature container started on port 5001"

echo "=== Step 8: Verify all containers ==="
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'

echo ""
echo "=== DUAL SETUP COMPLETE ==="
echo "Prod:    port 5000 -> tradeoptions.ngrok.app"
echo "Feature: port 5001 -> features-dev.ngrok.app (ngrok not started yet)"

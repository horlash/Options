#!/bin/bash
set -e

# Source env vars from .env file if present
[ -f /root/.env ] && export $(grep -v '^#' /root/.env | xargs)

echo "=== Create app_user on dev DB ==="
# Wait for postgres to be fully ready
for i in $(seq 1 10); do
    if docker exec paper_trading_db_dev pg_isready -U paper_user 2>/dev/null; then
        echo "Dev DB ready"
        break
    fi
    echo "Waiting... ($i)"
    sleep 2
done

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
echo "app_user created"

echo "=== Restore prod dump into dev DB ==="
docker exec -i paper_trading_db_dev psql -U paper_user -d paper_trading < /root/prod_dump.sql
echo "Dev DB loaded with prod data"

echo "=== Start feature container on port 5001 ==="
docker stop leap_scanner_feature 2>/dev/null && docker rm leap_scanner_feature 2>/dev/null || true

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

echo "Feature container started"

echo "=== Verify ==="
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
echo ""
echo "=== Start ngrok for feature dev ==="
# Kill any existing feature ngrok
pkill -f 'ngrok.*5001' 2>/dev/null || true
nohup ngrok http 5001 --domain=features-dev.ngrok.app --log=stdout > /root/ngrok_feature.log 2>&1 &
echo "NGROK_PID=$!"
sleep 3
echo "Ngrok for feature started"

echo ""
echo "=== ALL DONE ==="
echo "Prod:    http://localhost:5000 -> https://tradeoptions.ngrok.app"
echo "Feature: http://localhost:5001 -> https://features-dev.ngrok.app"

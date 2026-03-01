#!/bin/bash
set -e

# Source env vars from .env file if present
[ -f /root/.env ] && export $(grep -v '^#' /root/.env | xargs)

echo "=== Extract new feature code ==="
cd /root
rm -rf Options-build-latest
mkdir Options-build-latest
unzip -q Options-feature-latest.zip -d Options-build-latest
echo "Extracted"

echo "=== Build feature image ==="
cd Options-build-latest
docker build -t horlamy/newscanner:feature-test .

echo "=== Push to DockerHub ==="
docker push horlamy/newscanner:feature-test

echo "=== Restart feature container only ==="
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

echo "=== Verify ==="
sleep 5
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
echo ""
echo "=== Feature container logs ==="
docker logs --tail 10 leap_scanner_feature 2>&1
echo ""
echo "=== DONE — Prod untouched, feature updated ==="

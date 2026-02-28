#!/bin/bash
set -e

echo "=== Build feature image (--no-cache) ==="
cd /root/Options-build-latest
docker build --no-cache -t horlamy/newscanner:feature-test .

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
  -e SCHWAB_API_KEY='BBO22mnuVoTdTEptFGAMnpbPZi7h9PAHOshio0xu8NXh4cka' \
  -e SCHWAB_API_SECRET='uwVjRhbkbAZlBeG5quTXhCs8igjIfg2hFiJXQzAfG91yzYQnkxuhTtNA9ElESrz7' \
  -e FINNHUB_API_KEY='d5ksrbhr01qt47mfai40d5ksrbhr01qt47mfai4g' \
  -e FMP_API_KEY='jfB5vWaGzzEK6OowZayWNCxdbULnwROC' \
  -e SCHWAB_TOKEN_PATH=token.json \
  -e INTELLIGENCE_API_KEY='5EwFQfifLg1tYp4yBKxR0rZSuFlOumaAfHRTXtPxSZw' \
  -e PAPER_TRADE_DB_URL='postgresql://app_user:app_pass@paper_trading_db_dev:5432/paper_trading' \
  -e SECRET_KEY='dev-secret-key' \
  -e ORATS_API_KEY='b87b58de-a1bb-4958-accd-b4443ca61fdd' \
  -e PERPLEXITY_API_KEY='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' \
  -e ENCRYPTION_KEY='tEEt7rLBSnGazdFAMPmZ0GRXBDjqgqOUfHvnV65R8Uc=' \
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
docker logs --tail 20 leap_scanner_feature 2>&1
echo ""
echo "=== DONE — Prod untouched, feature updated (--no-cache) ==="

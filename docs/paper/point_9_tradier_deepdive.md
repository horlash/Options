# Point 9: Tradier Integration Architecture — Deep Dive (Double Deep)

> **Status:** FINALIZED ✅  
> **Date:** Feb 19, 2026  
> **Depends On:** Point 1 (Database), Point 4 (Brackets), Point 7 (Multi-User)

---

## 🎯 The Goal: "Switchable Reality"
A user can toggle between **Paper Trading (Sandbox)** and **Real Money (Live)** instantly.
The backend must not care *which* reality it is talking to. It just says "Buy AAPL".

---

## 🌐 Tradier API: The Two Worlds

### Base URLs
| Environment | Base URL | Purpose |
|-------------|----------|---------|
| **Sandbox** | `https://sandbox.tradier.com/v1/` | Paper trading, testing |
| **Live** | `https://api.tradier.com/v1/` | Real money trading |
| **Streaming** | `https://stream.tradier.com/v1/` | Live only (NOT available in Sandbox) |

### Authentication
Every request requires a Bearer token in the header:
```
Authorization: Bearer <ACCESS_TOKEN>
```
**⚠️ Critical:** Sandbox tokens and Live tokens are **NOT interchangeable**.
Using a Sandbox token on `api.tradier.com` returns `401 Unauthorized` with:
`"invalid api call as no apiproduct match found"`

---

## 🚦 Rate Limits (Per Token, Per Minute)

| Resource Type | Sandbox | Production |
|--------------|---------|------------|
| **Standard** (`/accounts`, `/orders` GET, `/watchlists`) | 60/min | 120/min |
| **Market Data** (`/markets`) | 60/min | 120/min |
| **Trading** (`/orders` POST, all trade scope) | 60/min | 60/min |

**Response Headers for Monitoring:**
```
X-Ratelimit-Allowed: 120
X-Ratelimit-Used: 15
X-Ratelimit-Available: 105
X-Ratelimit-Expiry: 1709856000
```

### Rate Limiter Implementation
```python
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls=50, period=60):
        # Use 50 instead of 60 to leave headroom
        self.timestamps = deque()
        self.max_calls = max_calls
        self.period = period
    
    def wait(self):
        now = time.time()
        # Remove expired timestamps
        while self.timestamps and now - self.timestamps[0] > self.period:
            self.timestamps.popleft()
        
        if len(self.timestamps) >= self.max_calls:
            sleep_time = self.period - (now - self.timestamps[0])
            time.sleep(sleep_time)
            
        self.timestamps.append(time.time())
```

---

## ⚠️ Error Handling: The "Silent Failure" Gotcha

### Standard HTTP Errors
| Code | Meaning | Our Response |
|------|---------|-------------|
| `400` | Bad Request (invalid params) | Log + Return user-friendly message |
| `401` | Wrong token or wrong environment | **CRITICAL:** Flag in UI as "Re-authenticate" |
| `403` | Insufficient permissions | Log + Block action |
| `429` | Rate limited | Auto-retry with backoff |
| `500` | Tradier internal error | Retry 2x, then alert |
| `503` | Tradier down/maintenance | Show "Broker Unavailable" banner |

### 🚨 The Critical Gotcha: "200 OK But Actually Failed"
**Problem:** When you place an order, Tradier returns `200 OK` **immediately**.
But the order might fail downstream (risk management, margin check, etc.).

**The Trap:**
```
POST /v1/accounts/{id}/orders → 200 OK  (You think it worked!)
GET  /v1/accounts/{id}/orders/{order_id} → { "status": "rejected", "errors": ["AccountMarginRuleViolation"] }
```

**The Fix:** We MUST poll the order status after placement.
```python
def place_and_confirm(self, order_request):
    # 1. Place the order
    order_id = self._place_order(order_request)
    
    # 2. Wait briefly for downstream processing
    time.sleep(1)
    
    # 3. Confirm the order status
    order = self._get_order(order_id)
    
    if order['status'] == 'rejected':
        raise BrokerException(
            f"Order rejected: {order.get('errors', 'Unknown reason')}"
        )
    
    return order
```

---

## 🏗️ The Architecture: Provider Pattern

### 1. The Abstract Base Class (`BrokerProvider`)
Defines the contract. Any broker (Schwab, IBKR) must implement this.

```python
# backend/services/broker/base.py
from abc import ABC, abstractmethod

class BrokerProvider(ABC):
    @abstractmethod
    def get_quotes(self, symbols: list) -> dict:
        """Get current quotes for a list of symbols."""
        pass
    
    @abstractmethod
    def get_option_chain(self, symbol: str, expiry: str) -> dict:
        """Get option chain for a symbol and expiration date."""
        pass

    @abstractmethod
    def place_order(self, order_request: dict) -> str:
        """Place an order. Returns order_id."""
        pass
    
    @abstractmethod
    def place_oco_order(self, leg1: dict, leg2: dict) -> dict:
        """Place a One-Cancels-Other order. Returns both order_ids."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """Get status of an existing order."""
        pass
    
    @abstractmethod
    def get_account_balance(self) -> dict:
        """Get account balance and buying power."""
        pass
```

### 2. The Concrete Implementation (`TradierBroker`)

```python
# backend/services/broker/tradier.py
import requests

class TradierBroker(BrokerProvider):
    SANDBOX_URL = "https://sandbox.tradier.com/v1"
    LIVE_URL = "https://api.tradier.com/v1"
    
    def __init__(self, access_token, account_id, is_live=False):
        self.token = access_token
        self.account_id = account_id
        self.base_url = self.LIVE_URL if is_live else self.SANDBOX_URL
        self.limiter = RateLimiter(max_calls=50, period=60)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }

    def get_quotes(self, symbols):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/markets/quotes",
            params={"symbols": ",".join(symbols)},
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["quotes"]["quote"]

    def place_order(self, order_request):
        self.limiter.wait()
        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_id}/orders",
            data=order_request,
            headers=self.headers
        )
        self._check_response(resp)
        order_id = resp.json()["order"]["id"]
        
        # CRITICAL: Confirm order wasn't silently rejected
        time.sleep(1)
        confirmation = self.get_order(order_id)
        if confirmation.get("status") == "rejected":
            raise BrokerException(
                f"Order rejected: {confirmation.get('errors')}"
            )
        return order_id

    def place_oco_order(self, sl_order, tp_order):
        """
        Tradier OCO: Two legs, one cancels the other.
        Used for SL/TP brackets (Point 4).
        """
        self.limiter.wait()
        payload = {
            "class": "oco",
            "duration": "gtc",
            # Leg 1: Stop Loss
            "side[0]": "sell_to_close",
            "symbol[0]": sl_order["symbol"],
            "quantity[0]": sl_order["qty"],
            "type[0]": "stop",
            "stop[0]": sl_order["stop_price"],
            # Leg 2: Take Profit
            "side[1]": "sell_to_close",
            "symbol[1]": tp_order["symbol"],
            "quantity[1]": tp_order["qty"],
            "type[1]": "limit",
            "price[1]": tp_order["limit_price"],
        }
        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_id}/orders",
            data=payload,
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["order"]

    def cancel_order(self, order_id):
        self.limiter.wait()
        resp = requests.delete(
            f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
            headers=self.headers
        )
        return resp.status_code == 200

    def get_order(self, order_id):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["order"]

    def get_account_balance(self):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_id}/balances",
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["balances"]
    
    def _check_response(self, resp):
        if resp.status_code == 401:
            raise BrokerAuthException("Invalid or expired token. Re-authenticate.")
        if resp.status_code == 429:
            raise BrokerRateLimitException("Rate limited. Retrying...")
        if resp.status_code >= 400:
            raise BrokerException(f"Tradier Error {resp.status_code}: {resp.text}")
```

---

## 🏭 The Factory: The "Switch"

How does the app know which broker context to use?

```python
# backend/services/broker/factory.py
class BrokerFactory:
    @staticmethod
    def get_broker(user: UserSettings) -> BrokerProvider:
        if user.broker_mode == 'LIVE':
            token = decrypt(user.tradier_live_token)
            is_live = True
        else:
            token = decrypt(user.tradier_sandbox_token)
            is_live = False
            
        return TradierBroker(
            access_token=token,
            account_id=user.tradier_account_id,
            is_live=is_live
        )
```

**Usage in Service Layer:**
```python
# backend/services/trade_service.py
def execute_trade(user, signal):
    broker = BrokerFactory.get_broker(user)  # <--- THE SWITCH
    order_id = broker.place_order({
        "class": "option",
        "symbol": signal["option_symbol"],
        "side": "buy_to_open",
        "quantity": signal["qty"],
        "type": "market",
        "duration": "day"
    })
    return order_id
```

---

## 🔑 Token Security: The "Vault" Strategy

**Problem:** API tokens stored in plain text in the DB = catastrophic if DB leaks.
**Solution:** Symmetric Encryption (Fernet).

```python
# backend/security/crypto.py
from cryptography.fernet import Fernet
import os

cipher = Fernet(os.getenv('ENCRYPTION_KEY'))

def encrypt(token: str) -> str:
    return cipher.encrypt(token.encode()).decode()

def decrypt(token_encrypted: str) -> str:
    return cipher.decrypt(token_encrypted.encode()).decode()
```

**Key Management:**
- `ENCRYPTION_KEY` is stored in Docker environment variables (never in code or DB).
- Generate once: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Rotate by re-encrypting all tokens with new key during maintenance window.

---

## 🧪 Sandbox Gotchas (Things That Will Bite You)

| Gotcha | Impact | Mitigation |
|--------|--------|------------|
| **15-min delayed quotes** | Prices are stale | Use ORATS for real-time snapshots (Point 2) |
| **No streaming** | Can't use WebSocket feeds | Polling only (already our V1 strategy) |
| **Weekly data wipes** | Test trades disappear | Our DB is the source of truth, not Tradier |
| **Different rate limits** | Sandbox=60/min vs Live=120/min | Use the lower limit (50/min) as our ceiling |
| **Tokens not interchangeable** | Using wrong token = instant 401 | Factory pattern prevents this by design |

---

## 🗂️ File Structure

```
backend/
├── services/
│   └── broker/
│       ├── __init__.py
│       ├── base.py          # BrokerProvider (ABC)
│       ├── tradier.py        # TradierBroker (Concrete)
│       ├── factory.py        # BrokerFactory
│       └── exceptions.py     # BrokerException, BrokerAuthException, etc.
├── security/
│   └── crypto.py             # encrypt() / decrypt()
└── utils/
    └── rate_limiter.py       # RateLimiter class
```

---

## Final Plan for Point 9

1.  **Architecture:** `BrokerProvider` (ABC) → `TradierBroker` (Concrete) → `BrokerFactory` (Switch).
2.  **Security:** Fernet encryption for all stored tokens.
3.  **Resilience:** Rate Limiter (50/min ceiling) + Auto-retry on 429.
4.  **Safety Net:** Post-placement confirmation poll (the "200 OK but rejected" gotcha).
5.  **OCO Orders:** Full payload format for SL/TP brackets.
6.  **Error Normalization:** All Tradier errors mapped to internal `BrokerException` hierarchy.

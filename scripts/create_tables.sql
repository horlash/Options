-- Create paper trading tables for Phase 5 deployment
-- Run as paper_user (superuser) to create tables and grant access to app_user

-- paper_trades
CREATE TABLE IF NOT EXISTS paper_trades (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(100) UNIQUE,
    ticker VARCHAR(10) NOT NULL,
    option_type VARCHAR(4) NOT NULL,
    strike FLOAT NOT NULL,
    expiry VARCHAR(10) NOT NULL,
    direction VARCHAR(4) DEFAULT 'BUY',
    entry_price FLOAT NOT NULL,
    qty INTEGER DEFAULT 1,
    sl_price FLOAT,
    tp_price FLOAT,
    strategy VARCHAR(20),
    card_score FLOAT,
    ai_score FLOAT,
    ai_verdict VARCHAR(20),
    gate_verdict VARCHAR(20),
    technical_score FLOAT,
    sentiment_score FLOAT,
    delta_at_entry FLOAT,
    iv_at_entry FLOAT,
    current_price FLOAT,
    unrealized_pnl FLOAT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','OPEN','PARTIALLY_FILLED','CLOSING','CLOSED','EXPIRED','CANCELED')),
    exit_price FLOAT,
    realized_pnl FLOAT,
    close_reason VARCHAR(30),
    trade_context JSONB NOT NULL DEFAULT '{}',
    broker_mode VARCHAR(20) DEFAULT 'TRADIER_SANDBOX',
    tradier_order_id VARCHAR(50),
    tradier_sl_order_id VARCHAR(50),
    tradier_tp_order_id VARCHAR(50),
    broker_fill_price FLOAT,
    broker_fill_time TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    is_locked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_paper_trades_username ON paper_trades(username);
CREATE INDEX IF NOT EXISTS ix_paper_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS ix_paper_trades_username_status ON paper_trades(username, status);
CREATE INDEX IF NOT EXISTS ix_paper_trades_username_ticker ON paper_trades(username, ticker);

-- state_transitions
CREATE TABLE IF NOT EXISTS state_transitions (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES paper_trades(id) ON DELETE CASCADE,
    from_status VARCHAR(20),
    to_status VARCHAR(20) NOT NULL,
    trigger VARCHAR(50) NOT NULL,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_state_transitions_trade_id ON state_transitions(trade_id);

-- price_snapshots
CREATE TABLE IF NOT EXISTS price_snapshots (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES paper_trades(id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    mark_price FLOAT,
    bid FLOAT,
    ask FLOAT,
    delta FLOAT,
    iv FLOAT,
    underlying FLOAT,
    snapshot_type VARCHAR(20) DEFAULT 'PERIODIC',
    username VARCHAR(50) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_price_snapshots_trade_id ON price_snapshots(trade_id);

-- user_settings
CREATE TABLE IF NOT EXISTS user_settings (
    username VARCHAR(50) PRIMARY KEY,
    broker_mode VARCHAR(20) DEFAULT 'TRADIER_SANDBOX',
    tradier_sandbox_token TEXT,
    tradier_live_token TEXT,
    tradier_account_id VARCHAR(50),
    account_balance FLOAT DEFAULT 5000.0,
    max_positions INTEGER DEFAULT 5,
    daily_loss_limit FLOAT DEFAULT 150.0,
    heat_limit_pct FLOAT DEFAULT 6.0,
    default_sl_pct FLOAT DEFAULT 20.0,
    default_tp_pct FLOAT DEFAULT 50.0,
    auto_refresh BOOLEAN DEFAULT TRUE,
    sound_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Grant all table permissions to app_user (RLS user)
GRANT SELECT, INSERT, UPDATE, DELETE ON paper_trades TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON state_transitions TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON price_snapshots TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_settings TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;

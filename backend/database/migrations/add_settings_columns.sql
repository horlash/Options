-- Settings Page Enhancement: Add 5 new columns
-- Run against both dev and prod databases

ALTER TABLE user_settings
  ADD COLUMN IF NOT EXISTS max_daily_trades INTEGER DEFAULT 10,
  ADD COLUMN IF NOT EXISTS theme VARCHAR(10) DEFAULT 'dark',
  ADD COLUMN IF NOT EXISTS alert_on_bracket_hit BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS auto_close_expiry BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS require_trade_confirm BOOLEAN DEFAULT TRUE;

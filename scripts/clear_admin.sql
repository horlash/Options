DELETE FROM state_transitions WHERE trade_id IN (SELECT id FROM paper_trades WHERE username = 'admin');
DELETE FROM price_snapshots WHERE username = 'admin';
DELETE FROM paper_trades WHERE username = 'admin';

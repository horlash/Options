"""
Monitor Service — The Engine
=============================
Phase 3: Core background engine that powers live trade monitoring.

Jobs:
  1. sync_tradier_orders()     — 60s — Check Tradier for fill/cancel events
  2. update_price_snapshots()  — 40s — Fetch ORATS prices, update P&L
  3. capture_bookend_snapshot() — 9:25 / 16:05 ET — Pre/Post market snapshots

Dependencies:
  - Phase 1: BrokerFactory, TradierBroker, PaperTrade, PriceSnapshot, UserSettings
  - Phase 3: market_hours (is_market_open)
"""

import logging
from datetime import datetime, timedelta, date, timezone

from sqlalchemy import text

from backend.database.paper_models import PaperTrade, PriceSnapshot, UserSettings, TradeStatus, StateTransition
from backend.database.paper_session import get_paper_db, get_paper_db_system
from backend.services.broker.factory import BrokerFactory
from backend.services.broker.exceptions import (
    BrokerException,
    BrokerAuthException,
    BrokerRateLimitException,
)
from backend.services.lifecycle import LifecycleManager, InvalidTransitionError
from backend.api.orats import OratsAPI
from backend.utils.market_hours import is_market_open, now_eastern, get_todays_market_close_utc

logger = logging.getLogger(__name__)


class MonitorService:
    """Central engine for trade monitoring."""

    LOCK_ID_SYNC_ORDERS = 100001
    LOCK_ID_PRICE_SNAPSHOTS = 100002
    LOCK_ID_LIFECYCLE_SYNC = 100003

    def __init__(self):
        self.orats = OratsAPI()

    def _compute_mfe_mae(self, db, trade):
        try:
            from backend.services.context_service import ContextService
            snapshots = (
                db.query(PriceSnapshot)
                .filter(PriceSnapshot.trade_id == trade.id)
                .order_by(PriceSnapshot.timestamp)
                .all()
            )
            if not snapshots:
                return
            ctx_service = ContextService(orats_api=self.orats)
            targets = ctx_service.calculate_targets(trade, snapshots)
            if targets:
                existing = dict(trade.trade_context or {})
                existing.update(targets)
                trade.trade_context = existing
        except Exception as e:
            logger.warning(f"Failed to compute MFE/MAE for trade {trade.id}: {e}")

    def _get_lifecycle(self, db):
        return LifecycleManager(db)

    def _log_transition(self, db, trade, from_status, to_status, trigger, metadata=None):
        transition = StateTransition(
            trade_id=trade.id,
            from_status=from_status,
            to_status=to_status,
            trigger=trigger,
            metadata_json=metadata or {},
        )
        db.add(transition)

    def _acquire_advisory_lock(self, db, lock_id):
        try:
            result = db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {'lock_id': lock_id}
            ).scalar()
            return bool(result)
        except Exception as e:
            logger.warning(f"Advisory lock acquisition failed: {e}")
            return True

    def _release_advisory_lock(self, db, lock_id):
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {'lock_id': lock_id}
            )
        except Exception as e:
            logger.warning(f"Advisory lock release failed: {e}")

    def sync_tradier_orders(self):
        if not is_market_open():
            return
        db = get_paper_db_system()
        if not self._acquire_advisory_lock(db, self.LOCK_ID_SYNC_ORDERS):
            db.close()
            return
        try:
            users_with_trades = (
                db.query(UserSettings)
                .filter(
                    UserSettings.username.in_(
                        db.query(PaperTrade.username)
                        .filter(PaperTrade.status == TradeStatus.OPEN.value)
                        .distinct()
                    )
                )
                .all()
            )
            for user_settings in users_with_trades:
                try:
                    self._sync_user_orders(db, user_settings)
                except BrokerAuthException as e:
                    logger.error(f"Auth error for {user_settings.username}: {e}.")
                except BrokerRateLimitException:
                    logger.warning(f"Rate limited for {user_settings.username}.")
                except BrokerException as e:
                    logger.error(f"Broker error syncing {user_settings.username}: {e}")
                except Exception as e:
                    logger.exception(f"Unexpected error syncing {user_settings.username}: {e}")
            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception(f"sync_tradier_orders failed: {e}")
        finally:
            self._release_advisory_lock(db, self.LOCK_ID_SYNC_ORDERS)
            db.close()

    def _sync_user_orders(self, db, user_settings):
        broker = BrokerFactory.get_broker(user_settings)
        open_trades = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.username == user_settings.username,
                PaperTrade.status == TradeStatus.OPEN.value,
                PaperTrade.tradier_order_id.isnot(None),
            )
            .all()
        )
        for trade in open_trades:
            try:
                order = broker.get_order(trade.tradier_order_id)
                status = (order.get('status') or '').lower()
                if status == 'filled':
                    self._handle_fill(db, trade, order)
                elif status == 'expired':
                    self._handle_expiration(db, trade)
                elif status in ('rejected', 'canceled'):
                    self._handle_cancellation(db, trade, status)
            except BrokerException as e:
                logger.warning(f"Could not sync order {trade.tradier_order_id} for trade {trade.id}: {e}")
        self._orphan_guard(db, broker, user_settings.username)

    def _handle_fill(self, db, trade, order):
        now = datetime.now(timezone.utc)
        fill_price = order.get('avg_fill_price') or order.get('price') or trade.entry_price
        fill_price = float(fill_price)
        close_reason = 'BROKER_FILL'
        if trade.sl_price and fill_price <= trade.sl_price * 1.02:
            close_reason = 'SL_HIT'
        elif trade.tp_price and fill_price >= trade.tp_price * 0.98:
            close_reason = 'TP_HIT'
        direction_mult = 1 if trade.direction == 'BUY' else -1
        realized_pnl = (fill_price - trade.entry_price) * trade.qty * 100 * direction_mult
        trade.exit_price = fill_price
        trade.realized_pnl = round(realized_pnl, 2)
        trade.close_reason = close_reason
        trade.broker_fill_price = fill_price
        trade.broker_fill_time = now
        lifecycle = self._get_lifecycle(db)
        lifecycle.transition(trade, TradeStatus.CLOSED, trigger='BROKER_FILL', metadata={'fill_price': fill_price, 'close_reason': close_reason, 'pnl': realized_pnl})
        self._compute_mfe_mae(db, trade)

    def _handle_expiration(self, db, trade):
        settings = db.query(UserSettings).filter_by(username=trade.username).first()
        auto_close = settings.auto_close_expiry if settings else True
        if auto_close:
            last_snap = (
                db.query(PriceSnapshot)
                .filter(PriceSnapshot.trade_id == trade.id)
                .order_by(PriceSnapshot.timestamp.desc())
                .first()
            )
            exit_price = last_snap.mark_price if last_snap and last_snap.mark_price else 0.0
            close_reason = 'EXPIRED_AUTO_CLOSE'
        else:
            exit_price = 0.0
            close_reason = 'EXPIRED'
        trade.exit_price = exit_price
        direction_mult = 1 if trade.direction == 'BUY' else -1
        trade.realized_pnl = round((exit_price - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
        trade.close_reason = close_reason
        lifecycle = self._get_lifecycle(db)
        lifecycle.transition(trade, TradeStatus.EXPIRED, trigger='BROKER_EXPIRED')

    def _handle_cancellation(self, db, trade, status):
        trade.close_reason = status.upper()
        lifecycle = self._get_lifecycle(db)
        try:
            lifecycle.transition(trade, TradeStatus.CANCELED, trigger=f'BROKER_{status.upper()}')
        except InvalidTransitionError:
            logger.warning(f"Trade {trade.id} in state {trade.status} cannot transition to CANCELED.")
            trade.status = TradeStatus.CANCELED.value
            trade.closed_at = datetime.now(timezone.utc)
            trade.version += 1
            self._log_transition(db, trade, from_status=trade.status, to_status=TradeStatus.CANCELED.value, trigger=f'BROKER_{status.upper()}_FORCED')

    def _orphan_guard(self, db, broker, username):
        closed_with_brackets = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.username == username,
                PaperTrade.status.in_([TradeStatus.CLOSED.value, TradeStatus.EXPIRED.value, TradeStatus.CANCELED.value]),
                (PaperTrade.tradier_sl_order_id.isnot(None) | PaperTrade.tradier_tp_order_id.isnot(None)),
            )
            .all()
        )
        for trade in closed_with_brackets:
            cancelled = False
            if trade.tradier_sl_order_id:
                try:
                    broker.cancel_order(trade.tradier_sl_order_id)
                    cancelled = True
                except BrokerException:
                    pass
                trade.tradier_sl_order_id = None
            if trade.tradier_tp_order_id:
                try:
                    broker.cancel_order(trade.tradier_tp_order_id)
                    cancelled = True
                except BrokerException:
                    pass
                trade.tradier_tp_order_id = None
            if cancelled:
                logger.info(f"Orphan Guard: cleaned up bracket orders for closed trade {trade.id} ({trade.ticker})")

    def update_price_snapshots(self):
        db = get_paper_db_system()
        try:
            open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN.value).all()
            if not open_trades:
                return
            if not is_market_open():
                from sqlalchemy import func
                trade_ids = [t.id for t in open_trades]
                last_snapshot_time = db.query(func.max(PriceSnapshot.timestamp)).filter(PriceSnapshot.trade_id.in_(trade_ids)).scalar()
                todays_close_utc = get_todays_market_close_utc()
                if last_snapshot_time and last_snapshot_time >= todays_close_utc:
                    return
            now = datetime.now(timezone.utc)

            # P1 CRIT-2: Daily loss circuit breaker
            from sqlalchemy import func as _func
            _today = datetime.now(timezone.utc).date()

            def _is_daily_loss_breached(username, user_settings_obj):
                if not user_settings_obj or not user_settings_obj.daily_loss_limit:
                    return False
                todays_realized = (
                    db.query(_func.coalesce(_func.sum(PaperTrade.realized_pnl), 0))
                    .filter(PaperTrade.username == username, PaperTrade.status == TradeStatus.CLOSED.value, _func.date(PaperTrade.closed_at) == _today)
                    .scalar()
                )
                return float(todays_realized or 0) <= -abs(user_settings_obj.daily_loss_limit)

            _user_settings_cache = {}

            def _get_user_settings(username):
                if username not in _user_settings_cache:
                    _user_settings_cache[username] = db.query(UserSettings).filter_by(username=username).first()
                return _user_settings_cache[username]

            for trade in open_trades:
                try:
                    # NEW-BUG-4 FIX: Define direction_mult at loop scope to prevent NameError in any branch
                    direction_mult = 1 if (trade.direction or 'BUY').upper() == 'BUY' else -1
                    expiry_str = str(trade.expiry) if trade.expiry else None
                    option_quote = None
                    if expiry_str and trade.strike and trade.option_type:
                        option_quote = self.orats.get_option_quote(trade.ticker, trade.strike, expiry_str, trade.option_type)
                    if option_quote:
                        mark = option_quote['mark']
                        bid = option_quote['bid']
                        ask = option_quote['ask']
                        underlying_price = option_quote['underlying']
                    else:
                        stock_quote = self.orats.get_quote(trade.ticker)
                        if not stock_quote:
                            continue
                        underlying_price = stock_quote.get('price', 0.0)
                        bid = stock_quote.get('bid')
                        ask = stock_quote.get('ask')
                        mark = (bid + ask) / 2 if bid and ask else underlying_price
                    snapshot = PriceSnapshot(trade_id=trade.id, timestamp=now, mark_price=mark, bid=bid, ask=ask, underlying=underlying_price, snapshot_type='PERIODIC', username=trade.username)
                    db.add(snapshot)
                    if option_quote:
                        trade.current_price = mark
                        trade.unrealized_pnl = round((mark - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
                    elif trade.current_price is not None:
                        pass  # direction_mult already defined at loop scope
                    else:
                        logger.info(f"No option quote for {trade.ticker} {trade.strike} {trade.option_type} — skipping price update")
                    trade.updated_at = now

                    # P2 BUG-P2: SL takes absolute priority over TP
                    close_reason = None
                    if option_quote:
                        if trade.sl_price and mark <= trade.sl_price:
                            close_reason = 'SL_HIT'
                        elif trade.tp_price and mark >= trade.tp_price:
                            close_reason = 'TP_HIT'

                    # P1 CRIT-2: Circuit breaker
                    # NEW-BUG-3 FIX: Only suppress SL_HIT (loss-extending) closes, not TP_HIT (profit-locking)
                    if close_reason == 'SL_HIT':
                        _us = _get_user_settings(trade.username)
                        if _is_daily_loss_breached(trade.username, _us):
                            logger.warning(f"[CIRCUIT BREAKER] Daily loss limit breached for {trade.username} — suppressing {close_reason} on trade {trade.id}.")
                            close_reason = None

                    if close_reason:
                        # CRIT-5 FIX: Re-query with FOR UPDATE to guard against concurrent
                        # manual close. If the trade is no longer OPEN, skip the auto-close.
                        locked_trade = (
                            db.query(PaperTrade)
                            .filter(
                                PaperTrade.id == trade.id,
                                PaperTrade.status == TradeStatus.OPEN.value,
                            )
                            .with_for_update()
                            .first()
                        )
                        if not locked_trade:
                            logger.info(
                                f"[CRIT-5] Trade {trade.id} ({trade.ticker}) is no longer OPEN — "
                                f"skipping {close_reason} auto-close (likely just manually closed)."
                            )
                            continue
                        locked_trade.exit_price = mark
                        locked_trade.realized_pnl = round((mark - locked_trade.entry_price) * locked_trade.qty * 100 * direction_mult, 2)
                        locked_trade.close_reason = close_reason
                        locked_trade.closed_at = now
                        lifecycle = self._get_lifecycle(db)
                        lifecycle.transition(locked_trade, TradeStatus.CLOSED, trigger=close_reason, metadata={'exit_price': mark, 'pnl': locked_trade.realized_pnl, 'trigger_price': mark})
                        self._compute_mfe_mae(db, locked_trade)

                except Exception as e:
                    logger.warning(f"Price snapshot failed for {trade.ticker} trade {trade.id}: {e}")

            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception(f"update_price_snapshots failed: {e}")
        finally:
            db.close()

    def capture_bookend_snapshot(self, snapshot_type='OPEN_BOOKEND'):
        db = get_paper_db_system()
        try:
            open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN.value).all()
            if not open_trades:
                return
            tickers = list(set(t.ticker for t in open_trades))
            now = datetime.now(timezone.utc)
            underlying_cache = {}
            for trade in open_trades:
                try:
                    ticker = trade.ticker
                    if ticker not in underlying_cache:
                        stock_quote = self.orats.get_quote(ticker)
                        underlying_cache[ticker] = stock_quote.get('price', 0.0) if stock_quote else 0.0
                    underlying_price = underlying_cache[ticker]
                    opt_quote = self.orats.get_option_quote(ticker=ticker, strike=trade.strike, expiry_date=trade.expiry, option_type=trade.option_type)
                    if opt_quote:
                        bid = opt_quote.get('bid', 0.0)
                        ask = opt_quote.get('ask', 0.0)
                        mark = opt_quote.get('mark', 0.0)
                        delta = opt_quote.get('delta')
                        iv = opt_quote.get('iv')
                    else:
                        bid = None
                        ask = None
                        mark = underlying_price
                        delta = None
                        iv = None
                    snapshot = PriceSnapshot(trade_id=trade.id, timestamp=now, mark_price=mark, bid=bid, ask=ask, underlying=underlying_price, delta=delta, iv=iv, snapshot_type=snapshot_type, username=trade.username)
                    db.add(snapshot)
                    trade.current_price = mark
                    direction_mult = 1 if trade.direction == 'BUY' else -1
                    trade.unrealized_pnl = round((mark - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
                except Exception as e:
                    logger.warning(f"Bookend snapshot failed for trade {trade.id} ({trade.ticker}): {e}")
            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception(f"capture_bookend_snapshot failed: {e}")
        finally:
            db.close()

    def manual_close_position(self, trade_id, username, db=None):
        from backend.database.paper_session import get_paper_db_with_user
        # CRIT-5 FIX: Accept an externally-supplied db session (with an existing FOR UPDATE
        # lock from close_trade in paper_routes.py). If none is provided, open a new session
        # and acquire the lock here to prevent concurrent auto-close races.
        _owns_session = db is None
        if _owns_session:
            db = get_paper_db_with_user(username)
        try:
            # CRIT-5 FIX: Use with_for_update() to ensure atomic read-then-write.
            # Re-verify status == OPEN after acquiring the lock so that if the monitoring
            # loop just closed this trade, we return early instead of double-closing.
            trade = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.id == trade_id,
                    PaperTrade.status == TradeStatus.OPEN.value,
                )
                .with_for_update()
                .first()
            )
            if not trade:
                logger.info(
                    f"[CRIT-5] manual_close_position: trade {trade_id} is no longer OPEN — "
                    f"skipping close (may have been auto-closed concurrently)."
                )
                return None
            user_settings = db.get(UserSettings, username)
            now = datetime.now(timezone.utc)
            if user_settings and trade.tradier_order_id:
                try:
                    broker = BrokerFactory.get_broker(user_settings)
                    if trade.tradier_sl_order_id:
                        try: broker.cancel_order(trade.tradier_sl_order_id)
                        except BrokerException: pass
                    if trade.tradier_tp_order_id:
                        try: broker.cancel_order(trade.tradier_tp_order_id)
                        except BrokerException: pass
                except BrokerException as e:
                    logger.warning(f"Broker error during manual close of trade {trade_id}: {e}")
            exit_price = None
            if trade.expiry and trade.strike and trade.option_type:
                try:
                    expiry_str = str(trade.expiry) if trade.expiry else None
                    option_quote = self.orats.get_option_quote(trade.ticker, trade.strike, expiry_str, trade.option_type)
                    if option_quote and option_quote.get('mark', 0) > 0:
                        exit_price = option_quote['mark']
                except Exception as e:
                    logger.warning(f"Failed to fetch fresh option quote: {e}")
            if exit_price is None:
                if trade.current_price and trade.current_price > trade.entry_price * 10 and trade.entry_price > 0:
                    exit_price = trade.entry_price
                else:
                    exit_price = trade.current_price or trade.entry_price
            if exit_price > trade.entry_price * 10 and trade.entry_price > 0:
                exit_price = trade.entry_price
            trade.exit_price = exit_price
            trade.close_reason = 'MANUAL_CLOSE'
            direction_mult = 1 if trade.direction == 'BUY' else -1
            trade.realized_pnl = round((trade.exit_price - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
            trade.tradier_sl_order_id = None
            trade.tradier_tp_order_id = None
            lifecycle = self._get_lifecycle(db)
            lifecycle.transition(trade, TradeStatus.CLOSED, trigger='USER_MANUAL_CLOSE', metadata={'exit_price': trade.exit_price, 'pnl': trade.realized_pnl})
            self._compute_mfe_mae(db, trade)
            db.commit()
            return {'id': trade.id, 'ticker': trade.ticker, 'exit_price': trade.exit_price, 'realized_pnl': trade.realized_pnl, 'status': trade.status}
        except Exception as e:
            db.rollback()
            logger.exception(f"manual_close_position failed: {e}")
            raise
        finally:
            # CRIT-5 FIX: Only close the session if this method opened it.
            # If a session was passed in (from close_trade), the caller owns the lifecycle.
            if _owns_session:
                db.close()

    def adjust_bracket(self, trade_id, username, new_sl=None, new_tp=None):
        from backend.database.paper_session import get_paper_db_with_user
        db = get_paper_db_with_user(username)
        try:
            trade = db.query(PaperTrade).filter(PaperTrade.id == trade_id, PaperTrade.status == TradeStatus.OPEN.value).first()
            if not trade:
                return None
            if new_sl is not None: trade.sl_price = float(new_sl)
            if new_tp is not None: trade.tp_price = float(new_tp)
            user_settings = db.get(UserSettings, username)
            if user_settings and trade.tradier_order_id:
                broker = None
                cancel_succeeded = False
                try:
                    broker = BrokerFactory.get_broker(user_settings)
                    if trade.tradier_sl_order_id: broker.cancel_order(trade.tradier_sl_order_id)
                    if trade.tradier_tp_order_id: broker.cancel_order(trade.tradier_tp_order_id)
                    cancel_succeeded = True
                    trade.tradier_sl_order_id = None
                    trade.tradier_tp_order_id = None
                    if trade.sl_price and trade.tp_price:
                        occ_symbol = self._build_occ_symbol(trade)
                        oco = broker.place_oco_order(sl_order={'symbol': occ_symbol, 'quantity': trade.qty, 'stop': trade.sl_price}, tp_order={'symbol': occ_symbol, 'quantity': trade.qty, 'price': trade.tp_price})
                        legs = oco.get('leg', [])
                        if len(legs) >= 2:
                            trade.tradier_sl_order_id = str(legs[0].get('id', ''))
                            trade.tradier_tp_order_id = str(legs[1].get('id', ''))
                except BrokerException as e:
                    if cancel_succeeded:
                        logger.critical(f"BRACKET GAP: Trade {trade_id} ({trade.ticker}) — old OCO cancelled but new OCO failed: {e}. Position is UNPROTECTED.")
                        # P2 BUG-F2: Persist unprotected flag
                        ctx = dict(trade.trade_context or {})
                        ctx['unprotected'] = True
                        ctx['unprotected_reason'] = f'Bracket recreate failed: {e}'
                        ctx['unprotected_at'] = datetime.now(timezone.utc).isoformat()
                        trade.trade_context = ctx
                    else:
                        logger.warning(f"Broker error adjusting bracket for trade {trade_id}: {e}")
                except Exception as e:
                    if cancel_succeeded:
                        logger.critical(f"BRACKET GAP: Trade {trade_id} ({trade.ticker}) — unexpected error after cancel: {e}.")
                        ctx = dict(trade.trade_context or {})
                        ctx['unprotected'] = True
                        ctx['unprotected_reason'] = f'Bracket recreate error: {e}'
                        ctx['unprotected_at'] = datetime.now(timezone.utc).isoformat()
                        trade.trade_context = ctx
                    else:
                        logger.exception(f"Unexpected error in bracket adjust for trade {trade_id}: {e}")
            trade.version += 1
            trade.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {'id': trade.id, 'ticker': trade.ticker, 'sl_price': trade.sl_price, 'tp_price': trade.tp_price, 'version': trade.version}
        except Exception as e:
            db.rollback()
            logger.exception(f"adjust_bracket failed: {e}")
            raise
        finally:
            db.close()

    def lifecycle_sync(self):
        if not is_market_open():
            return
        db = get_paper_db_system()
        if not self._acquire_advisory_lock(db, self.LOCK_ID_LIFECYCLE_SYNC):
            db.close()
            return
        lifecycle = self._get_lifecycle(db)
        try:
            pending_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.PENDING.value, PaperTrade.tradier_order_id.isnot(None)).all()
            for trade in pending_trades:
                try:
                    user_settings = db.get(UserSettings, trade.username)
                    if not user_settings: continue
                    broker = BrokerFactory.get_broker(user_settings)
                    order = broker.get_order(trade.tradier_order_id)
                    status = (order.get('status') or '').lower()
                    if status == 'filled':
                        trade.entry_price = float(order.get('avg_fill_price') or trade.entry_price)
                        trade.broker_fill_price = trade.entry_price
                        trade.broker_fill_time = datetime.now(timezone.utc)
                        lifecycle.transition(trade, TradeStatus.OPEN, trigger='CRON_FILL_CHECK', metadata={'fill_price': trade.entry_price})
                    elif status == 'partially_filled':
                        lifecycle.transition(trade, TradeStatus.PARTIALLY_FILLED, trigger='CRON_FILL_CHECK', metadata={'filled_qty': order.get('filled_quantity', trade.qty)})
                    elif status in ('canceled', 'rejected'):
                        lifecycle.transition(trade, TradeStatus.CANCELED, trigger='CRON_FILL_CHECK', metadata={'reason': order.get('reason', status)})
                except BrokerException as e:
                    logger.warning(f"lifecycle_sync: broker error on PENDING trade {trade.id}: {e}")
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            closing_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.CLOSING.value, PaperTrade.tradier_order_id.isnot(None)).all()
            for trade in closing_trades:
                try:
                    user_settings = db.query(UserSettings).filter_by(username=trade.username).first()
                    if not user_settings: continue
                    broker = BrokerFactory.get_broker(user_settings)
                    order = broker.get_order(trade.tradier_order_id)
                    status = (order.get('status') or '').lower()
                    if status == 'filled':
                        trade.exit_price = float(order.get('avg_fill_price') or trade.current_price or trade.entry_price)
                        direction_mult = 1 if trade.direction == 'BUY' else -1
                        trade.realized_pnl = round((trade.exit_price - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
                        trade.close_reason = 'BROKER_FILL'
                        lifecycle.transition(trade, TradeStatus.CLOSED, trigger='CRON_CLOSE_FILL', metadata={'fill_price': trade.exit_price})
                    elif status == 'rejected':
                        lifecycle.transition(trade, TradeStatus.OPEN, trigger='CRON_CLOSE_REJECTED', metadata={'reason': order.get('reason', 'rejected')})
                except BrokerException as e:
                    logger.warning(f"lifecycle_sync: broker error on CLOSING trade {trade.id}: {e}")
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            # P3 BUG-L2: Normalize expiry date format
            today_str = date.today().isoformat()
            expired_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.OPEN.value, PaperTrade.expiry <= today_str).all()

            def _normalize_expiry_date(raw):
                if not raw: return None
                raw = str(raw).strip()
                if len(raw) == 10 and raw[4] == '-' and raw[7] == '-': return raw
                try:
                    from dateutil import parser as _dp
                    return _dp.parse(raw).strftime('%Y-%m-%d')
                except Exception:
                    return raw

            for trade in expired_trades:
                try:
                    normalized_expiry = _normalize_expiry_date(trade.expiry)
                    if normalized_expiry and normalized_expiry > today_str:
                        continue
                    if trade.current_price is not None and trade.current_price <= 0.05:
                        trade.exit_price = 0.0
                        # P3 BUG-L3: Direction-aware P&L in expiry path
                        direction_mult = 1 if (trade.direction or 'BUY').upper() == 'BUY' else -1
                        trade.realized_pnl = round((0.0 - trade.entry_price) * trade.qty * 100 * direction_mult, 2)
                        trade.close_reason = 'EXPIRED'
                        lifecycle.transition(trade, TradeStatus.EXPIRED, trigger='CRON_EXPIRY_CHECK', metadata={'last_price': trade.current_price})
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            db.commit()
            try:
                for user_settings in db.query(UserSettings).all():
                    try:
                        broker = BrokerFactory.get_broker(user_settings)
                        self._orphan_guard(db, broker, user_settings.username)
                    except Exception as e:
                        logger.debug(f"lifecycle_sync orphan guard skip for {user_settings.username}: {e}")
                db.commit()
            except Exception as e:
                logger.debug(f"lifecycle_sync orphan guard error: {e}")

        except Exception as e:
            db.rollback()
            logger.exception(f"lifecycle_sync failed: {e}")
        finally:
            self._release_advisory_lock(db, self.LOCK_ID_LIFECYCLE_SYNC)
            db.close()

    @staticmethod
    def _build_occ_symbol(trade):
        expiry = trade.expiry
        if isinstance(expiry, str):
            expiry_dt = datetime.strptime(expiry, '%Y-%m-%d')
        elif hasattr(expiry, 'strftime'):
            expiry_dt = expiry
        else:
            expiry_dt = datetime.strptime(str(expiry), '%Y-%m-%d')
        opt_type = 'C' if trade.option_type.upper() == 'CALL' else 'P'
        strike_padded = f"{int(trade.strike * 1000):08d}"
        return f"{trade.ticker}{expiry_dt.strftime('%y%m%d')}{opt_type}{strike_padded}"

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
from datetime import datetime, timedelta

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
    """Central engine for trade monitoring.

    Designed to be called by APScheduler at fixed intervals.
    Each method acquires its own DB session and commits/rolls back independently.
    """

    # Advisory lock IDs for cron overlap prevention (Point 10)
    # Reserved range: 100001–100099 for MonitorService.
    # These must be globally unique across all Postgres advisory lock users.
    # If adding new locks, increment from the last used ID.
    LOCK_ID_SYNC_ORDERS = 100001      # sync_tradier_orders()
    LOCK_ID_PRICE_SNAPSHOTS = 100002  # update_price_snapshots()
    LOCK_ID_LIFECYCLE_SYNC = 100003   # lifecycle_sync()

    def __init__(self):
        self.orats = OratsAPI()

    def _compute_mfe_mae(self, db, trade):
        """Compute MFE/MAE from price snapshots and merge into trade_context.

        Called after a trade is closed (any path) to populate
        trade_context.mfe / trade_context.mae for the frontend.
        """
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
                logger.info(
                    f"MFE/MAE stored for trade {trade.id}: "
                    f"mfe=${targets.get('mfe')}, mae=${targets.get('mae')}"
                )
        except Exception as e:
            logger.warning(f"Failed to compute MFE/MAE for trade {trade.id}: {e}")

    def _get_lifecycle(self, db):
        """Get a LifecycleManager bound to the given DB session."""
        return LifecycleManager(db)

    def _log_transition(self, db, trade, from_status, to_status, trigger, metadata=None):
        """Record every status change in the audit trail (Point 11).

        NOTE: Kept for backward compatibility. New code should use
        LifecycleManager.transition() which logs automatically.
        """
        transition = StateTransition(
            trade_id=trade.id,
            from_status=from_status,
            to_status=to_status,
            trigger=trigger,
            metadata_json=metadata or {},
        )
        db.add(transition)
        logger.debug(
            f"StateTransition: trade {trade.id} {from_status}->{to_status} via {trigger}"
        )

    def _acquire_advisory_lock(self, db, lock_id):
        """Try to acquire a PostgreSQL advisory lock (Point 10).

        Returns True if lock acquired, False if another process holds it.
        Advisory locks are session-level and auto-release on session close.
        """
        try:
            result = db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {'lock_id': lock_id}
            ).scalar()
            return bool(result)
        except Exception as e:
            logger.warning(f"Advisory lock acquisition failed: {e}")
            return True  # Proceed anyway if lock mechanism unavailable

    def _release_advisory_lock(self, db, lock_id):
        """Release a PostgreSQL advisory lock."""
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {'lock_id': lock_id}
            )
        except Exception as e:
            logger.warning(f"Advisory lock release failed: {e}")

    # ─────────────────────────────────────────────────────────────
    # Job 1: Sync Tradier Orders (every 60s)
    # ─────────────────────────────────────────────────────────────

    def sync_tradier_orders(self):
        """Check Tradier for order fills/cancellations and update DB.

        For each OPEN trade that has a tradier_order_id:
          - Fetch order status from Tradier
          - If filled → close trade, record fill price + P&L
          - If expired → mark as EXPIRED
          - If rejected → mark as CANCELED

        Also runs the Orphan Guard: checks for closed trades with
        lingering SL/TP bracket orders and cancels them.

        Uses advisory lock (Point 10) to prevent overlapping executions.
        """
        if not is_market_open():
            return

        db = get_paper_db_system()
        if not self._acquire_advisory_lock(db, self.LOCK_ID_SYNC_ORDERS):
            logger.debug("sync_tradier_orders skipped — another instance holds the lock.")
            db.close()
            return
        try:
            # Get all users with open trades
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
                    logger.error(
                        f"Auth error for {user_settings.username}: {e}. "
                        f"Token may be expired."
                    )
                except BrokerRateLimitException:
                    logger.warning(
                        f"Rate limited for {user_settings.username}, "
                        f"will retry next cycle."
                    )
                except BrokerException as e:
                    logger.error(
                        f"Broker error syncing {user_settings.username}: {e}"
                    )
                except Exception as e:
                    logger.exception(
                        f"Unexpected error syncing {user_settings.username}: {e}"
                    )

            db.commit()
            logger.debug("sync_tradier_orders completed successfully.")

        except Exception as e:
            db.rollback()
            logger.exception(f"sync_tradier_orders failed: {e}")
        finally:
            self._release_advisory_lock(db, self.LOCK_ID_SYNC_ORDERS)
            db.close()

    def _sync_user_orders(self, db, user_settings):
        """Sync all open trades for a single user."""
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
                logger.warning(
                    f"Could not sync order {trade.tradier_order_id} "
                    f"for trade {trade.id}: {e}"
                )

        # Orphan Guard: cancel bracket orders for already-closed trades
        self._orphan_guard(db, broker, user_settings.username)

    def _handle_fill(self, db, trade, order):
        """Process a filled order — mark trade as closed with P&L."""
        now = datetime.utcnow()

        fill_price = order.get('avg_fill_price') or order.get('price') or trade.entry_price
        fill_price = float(fill_price)

        # Determine close reason by checking which bracket leg was filled
        close_reason = 'BROKER_FILL'
        if trade.sl_price and fill_price <= trade.sl_price * 1.02:
            close_reason = 'SL_HIT'
        elif trade.tp_price and fill_price >= trade.tp_price * 0.98:
            close_reason = 'TP_HIT'

        # Calculate realized P&L
        direction_mult = 1 if trade.direction == 'BUY' else -1
        realized_pnl = (fill_price - trade.entry_price) * trade.qty * 100 * direction_mult

        # Set trade fields before lifecycle transition
        trade.exit_price = fill_price
        trade.realized_pnl = round(realized_pnl, 2)
        trade.close_reason = close_reason
        trade.broker_fill_price = fill_price
        trade.broker_fill_time = now

        # Lifecycle transition: OPEN → CLOSED (Point 11)
        lifecycle = self._get_lifecycle(db)
        lifecycle.transition(
            trade, TradeStatus.CLOSED,
            trigger='BROKER_FILL',
            metadata={'fill_price': fill_price, 'close_reason': close_reason, 'pnl': realized_pnl},
        )

        logger.info(
            f"Trade {trade.id} ({trade.ticker}) FILLED at ${fill_price:.2f} — "
            f"P&L: ${realized_pnl:+.2f} ({close_reason})"
        )

        # Compute MFE/MAE from price history
        self._compute_mfe_mae(db, trade)

    def _handle_expiration(self, db, trade):
        """Auto-close expired position at last known market price or force $0."""
        # Check user preference for auto-close behavior
        settings = db.query(UserSettings).filter_by(username=trade.username).first()
        auto_close = settings.auto_close_expiry if settings else True

        if auto_close:
            # Use last polled price (reflects intrinsic value for ITM options)
            last_snap = (
                db.query(PriceSnapshot)
                .filter(PriceSnapshot.trade_id == trade.id)
                .order_by(PriceSnapshot.timestamp.desc())
                .first()
            )
            exit_price = last_snap.mark_price if last_snap and last_snap.mark_price else 0.0
            close_reason = 'EXPIRED_AUTO_CLOSE'
        else:
            # Legacy behavior: expire worthless
            exit_price = 0.0
            close_reason = 'EXPIRED'

        trade.exit_price = exit_price
        # F21 FIX: Add direction_mult — previously always assumed BUY direction
        direction_mult = 1 if trade.direction == 'BUY' else -1
        trade.realized_pnl = round(
            (exit_price - trade.entry_price) * trade.qty * 100 * direction_mult, 2
        )
        trade.close_reason = close_reason

        # Lifecycle transition: OPEN → EXPIRED (Point 11)
        lifecycle = self._get_lifecycle(db)
        lifecycle.transition(
            trade, TradeStatus.EXPIRED,
            trigger='BROKER_EXPIRED',
        )

        logger.info(f"Trade {trade.id} ({trade.ticker}) {close_reason} @ ${exit_price}")

    def _handle_cancellation(self, db, trade, status):
        """Handle a rejected or canceled order."""
        trade.close_reason = status.upper()

        # Lifecycle transition: OPEN → CANCELED (Point 11)
        # Note: OPEN → CANCELED is allowed via VALID_TRANSITIONS
        # for broker-level cancellations/rejections of open positions
        lifecycle = self._get_lifecycle(db)
        try:
            lifecycle.transition(
                trade, TradeStatus.CANCELED,
                trigger=f'BROKER_{status.upper()}',
            )
        except InvalidTransitionError:
            # If trade is not in an allowed state for cancellation,
            # fall back to direct assignment (safety net)
            logger.warning(
                f"Trade {trade.id} in state {trade.status} cannot transition to CANCELED. "
                f"Applying direct assignment as fallback."
            )
            trade.status = TradeStatus.CANCELED.value
            trade.closed_at = datetime.utcnow()
            trade.version += 1
            self._log_transition(
                db, trade,
                from_status=trade.status,
                to_status=TradeStatus.CANCELED.value,
                trigger=f'BROKER_{status.upper()}_FORCED',
            )

        logger.info(f"Trade {trade.id} ({trade.ticker}) {status.upper()}.")

    def _orphan_guard(self, db, broker, username):
        """Cancel any bracket orders still open for already-closed trades.

        This catches edge cases where:
          - A trade was manually closed, but SL/TP orders weren't cancelled
          - A network glitch prevented bracket cancellation
        """
        closed_with_brackets = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.username == username,
                PaperTrade.status.in_([
                    TradeStatus.CLOSED.value,
                    TradeStatus.EXPIRED.value,
                    TradeStatus.CANCELED.value,
                ]),
                (
                    PaperTrade.tradier_sl_order_id.isnot(None) |
                    PaperTrade.tradier_tp_order_id.isnot(None)
                ),
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
                    pass  # Already cancelled or filled — fine
                trade.tradier_sl_order_id = None

            if trade.tradier_tp_order_id:
                try:
                    broker.cancel_order(trade.tradier_tp_order_id)
                    cancelled = True
                except BrokerException:
                    pass
                trade.tradier_tp_order_id = None

            if cancelled:
                logger.info(
                    f"Orphan Guard: cleaned up bracket orders for "
                    f"closed trade {trade.id} ({trade.ticker})"
                )

    # ─────────────────────────────────────────────────────────────
    # Job 2: Update Price Snapshots (every 40s)
    # ─────────────────────────────────────────────────────────────

    def update_price_snapshots(self):
        """Fetch current prices and update P&L for all open trades.

        Uses ORATS for real-time option pricing (not Tradier, which has
        15-min delay in sandbox). Updates:
          1. PriceSnapshot table (for P&L charts)
          2. PaperTrade.current_price + unrealized_pnl (for UI)

        Smart after-hours guard (DB-backed):
          - Market open:  fetch every 40s (normal)
          - Market closed: check last snapshot timestamp in DB
            - If last snapshot < today's 4 PM ET → fetch once (closing price)
            - If last snapshot >= today's 4 PM ET → skip (already have close)
        """
        db = get_paper_db_system()
        try:
            open_trades = (
                db.query(PaperTrade)
                .filter(PaperTrade.status == TradeStatus.OPEN.value)
                .all()
            )

            if not open_trades:
                return

            # Smart after-hours guard: only fetch closing price once
            if not is_market_open():
                # Check when the most recent snapshot was taken
                from sqlalchemy import func
                trade_ids = [t.id for t in open_trades]
                last_snapshot_time = (
                    db.query(func.max(PriceSnapshot.timestamp))
                    .filter(PriceSnapshot.trade_id.in_(trade_ids))
                    .scalar()
                )

                todays_close_utc = get_todays_market_close_utc()

                if last_snapshot_time and last_snapshot_time >= todays_close_utc:
                    # Already have a post-close snapshot — skip
                    logger.debug(
                        "After-hours: closing price already captured "
                        f"(last snapshot: {last_snapshot_time}). Skipping."
                    )
                    return

                logger.info(
                    "After-hours: no post-close snapshot found. "
                    "Fetching closing prices for open trades."
                )

            now = datetime.utcnow()

            for trade in open_trades:
                try:
                    expiry_str = str(trade.expiry) if trade.expiry else None

                    # Try contract-specific quote first (exact option price)
                    option_quote = None
                    if expiry_str and trade.strike and trade.option_type:
                        option_quote = self.orats.get_option_quote(
                            trade.ticker,
                            trade.strike,
                            expiry_str,
                            trade.option_type,
                        )

                    if option_quote:
                        mark = option_quote['mark']
                        bid = option_quote['bid']
                        ask = option_quote['ask']
                        underlying_price = option_quote['underlying']
                    else:
                        # Fallback: use stock quote (better than nothing)
                        stock_quote = self.orats.get_quote(trade.ticker)
                        if not stock_quote:
                            logger.warning(
                                f"ORATS returned no data for {trade.ticker}, skipping."
                            )
                            continue
                        underlying_price = stock_quote.get('price', 0.0)
                        bid = stock_quote.get('bid')
                        ask = stock_quote.get('ask')
                        mark = (bid + ask) / 2 if bid and ask else underlying_price

                    # Write PriceSnapshot
                    snapshot = PriceSnapshot(
                        trade_id=trade.id,
                        timestamp=now,
                        mark_price=mark,
                        bid=bid,
                        ask=ask,
                        underlying=underlying_price,
                        snapshot_type='PERIODIC',
                        username=trade.username,
                    )
                    db.add(snapshot)

                    # Update live fields on PaperTrade
                    # Only set current_price from option quotes, NOT stock fallback
                    # This prevents stock price ($272) from contaminating option price ($2.92)
                    if option_quote:
                        trade.current_price = mark
                        direction_mult = 1 if trade.direction == 'BUY' else -1
                        trade.unrealized_pnl = round(
                            (mark - trade.entry_price) * trade.qty * 100 * direction_mult,
                            2,
                        )
                    elif trade.current_price is not None:
                        # Stock fallback: keep existing option price, just update timestamp
                        direction_mult = 1 if trade.direction == 'BUY' else -1
                        # P&L stays based on last known option price
                    else:
                        # No option quote AND no previous price: skip price update
                        logger.info(
                            f"No option quote for {trade.ticker} {trade.strike} "
                            f"{trade.option_type} — skipping price update"
                        )
                    trade.updated_at = now

                    # ── Paper SL/TP Auto-Close ──
                    # Only check SL/TP thresholds with option-level prices, NOT stock fallback
                    # (stock price $272 would falsely trigger TP set at $10)
                    close_reason = None
                    if option_quote:
                        if trade.tp_price and mark >= trade.tp_price:
                            close_reason = 'TP_HIT'
                        elif trade.sl_price and mark <= trade.sl_price:
                            close_reason = 'SL_HIT'

                    if close_reason:
                        trade.exit_price = mark
                        trade.realized_pnl = round(
                            (mark - trade.entry_price) * trade.qty * 100 * direction_mult,
                            2,
                        )
                        trade.close_reason = close_reason
                        trade.closed_at = now

                        lifecycle = self._get_lifecycle(db)
                        lifecycle.transition(
                            trade, TradeStatus.CLOSED,
                            trigger=close_reason,
                            metadata={
                                'exit_price': mark,
                                'pnl': trade.realized_pnl,
                                'trigger_price': mark,
                            },
                        )

                        logger.info(
                            f"[AUTO-CLOSE] {close_reason}: Trade {trade.id} "
                            f"({trade.ticker}) closed at ${mark:.2f}, "
                            f"P&L: ${trade.realized_pnl:+.2f}"
                        )

                        # Compute MFE/MAE from price history
                        self._compute_mfe_mae(db, trade)

                except Exception as e:
                    logger.warning(
                        f"Price snapshot failed for {trade.ticker} trade {trade.id}: {e}"
                    )

            db.commit()
            logger.debug(
                f"Price snapshots updated for {len(open_trades)} trades."
            )

        except Exception as e:
            db.rollback()
            logger.exception(f"update_price_snapshots failed: {e}")
        finally:
            db.close()

    # ─────────────────────────────────────────────────────────────
    # Job 3: Bookend Snapshots (9:25 AM, 4:05 PM ET)
    # ─────────────────────────────────────────────────────────────

    def capture_bookend_snapshot(self, snapshot_type='OPEN_BOOKEND'):
        """Capture a pre-market or post-market price snapshot.

        Args:
            snapshot_type: 'OPEN_BOOKEND' (9:25 AM) or 'CLOSE_BOOKEND' (4:05 PM)

        These bookend snapshots capture:
          - Gap-ups/downs from overnight (pre-market)
          - Official mark-to-market close (post-market)
        """
        db = get_paper_db_system()
        try:
            open_trades = (
                db.query(PaperTrade)
                .filter(PaperTrade.status == TradeStatus.OPEN.value)
                .all()
            )

            if not open_trades:
                return

            tickers = list(set(t.ticker for t in open_trades))
            now = datetime.utcnow()

            logger.info(
                f"Capturing {snapshot_type} for {len(open_trades)} trades "
                f"({len(tickers)} tickers)"
            )

            # P0-14 FIX: Fetch option-level prices per trade, not stock prices.
            # Cache underlying prices per ticker to avoid redundant API calls.
            underlying_cache = {}

            for trade in open_trades:
                try:
                    ticker = trade.ticker

                    # Get underlying stock price (cached per ticker)
                    if ticker not in underlying_cache:
                        stock_quote = self.orats.get_quote(ticker)
                        underlying_cache[ticker] = (
                            stock_quote.get('price', 0.0) if stock_quote else 0.0
                        )
                    underlying_price = underlying_cache[ticker]

                    # Fetch the OPTION contract's bid/ask/mark
                    opt_quote = self.orats.get_option_quote(
                        ticker=ticker,
                        strike=trade.strike,
                        expiry_date=trade.expiry,
                        option_type=trade.option_type,
                    )

                    if opt_quote:
                        bid = opt_quote.get('bid', 0.0)
                        ask = opt_quote.get('ask', 0.0)
                        mark = opt_quote.get('mark', 0.0)
                        delta = opt_quote.get('delta')
                        iv = opt_quote.get('iv')
                    else:
                        # Fallback: use stock price if option quote unavailable
                        logger.warning(
                            f"Option quote unavailable for {ticker} "
                            f"{trade.strike} {trade.expiry} {trade.option_type}, "
                            f"falling back to underlying price"
                        )
                        bid = None
                        ask = None
                        mark = underlying_price
                        delta = None
                        iv = None

                    snapshot = PriceSnapshot(
                        trade_id=trade.id,
                        timestamp=now,
                        mark_price=mark,
                        bid=bid,
                        ask=ask,
                        underlying=underlying_price,
                        delta=delta,
                        iv=iv,
                        snapshot_type=snapshot_type,
                        username=trade.username,
                    )
                    db.add(snapshot)

                    # Also update the live price on the trade
                    trade.current_price = mark
                    direction_mult = 1 if trade.direction == 'BUY' else -1
                    trade.unrealized_pnl = round(
                        (mark - trade.entry_price) * trade.qty * 100 * direction_mult,
                        2,
                    )

                except Exception as e:
                    logger.warning(
                        f"Bookend snapshot failed for trade {trade.id} ({trade.ticker}): {e}"
                    )

            db.commit()
            logger.info(f"{snapshot_type} complete for {len(tickers)} tickers.")

        except Exception as e:
            db.rollback()
            logger.exception(f"capture_bookend_snapshot failed: {e}")
        finally:
            db.close()

    # ─────────────────────────────────────────────────────────────
    # Manual Actions (Called by API routes)
    # ─────────────────────────────────────────────────────────────

    def manual_close_position(self, trade_id, username):
        """Close a position manually from the UI.

        1. Place market sell via Tradier
        2. Cancel orphaned SL/TP bracket orders
        3. Update DB

        Args:
            trade_id: PaperTrade.id
            username: Current user (for RLS)

        Returns:
            Updated PaperTrade dict or None if not found
        """
        from backend.database.paper_session import get_paper_db_with_user

        db = get_paper_db_with_user(username)
        try:
            trade = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.id == trade_id,
                    PaperTrade.status == TradeStatus.OPEN.value,
                )
                .first()
            )

            if not trade:
                return None

            # Get user's broker
            user_settings = db.get(UserSettings, username)
            now = datetime.utcnow()

            if user_settings and trade.tradier_order_id:
                try:
                    broker = BrokerFactory.get_broker(user_settings)

                    # Cancel SL/TP bracket orders immediately
                    if trade.tradier_sl_order_id:
                        try:
                            broker.cancel_order(trade.tradier_sl_order_id)
                        except BrokerException:
                            pass
                    if trade.tradier_tp_order_id:
                        try:
                            broker.cancel_order(trade.tradier_tp_order_id)
                        except BrokerException:
                            pass

                except BrokerException as e:
                    logger.warning(
                        f"Broker error during manual close of trade {trade_id}: {e}"
                    )

            # Close the trade in DB — try fresh option quote first (handles market-closed scenario)
            exit_price = None

            # Attempt fresh option quote from ORATS
            if trade.expiry and trade.strike and trade.option_type:
                try:
                    expiry_str = str(trade.expiry) if trade.expiry else None
                    option_quote = self.orats.get_option_quote(
                        trade.ticker, trade.strike, expiry_str, trade.option_type
                    )
                    if option_quote and option_quote.get('mark', 0) > 0:
                        exit_price = option_quote['mark']
                        logger.info(
                            f"Fresh option quote for {trade.ticker}: ${exit_price:.2f}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to fetch fresh option quote: {e}")

            # Fallback chain: fresh quote → last known option price → entry price
            if exit_price is None:
                # Guard current_price from stock fallback if it's clearly a stock price
                if trade.current_price and trade.current_price > trade.entry_price * 5 and trade.entry_price > 0:
                    logger.warning(
                        f"trade.current_price ${trade.current_price:.2f} is >5x entry ${trade.entry_price:.2f} "
                        f"for {trade.ticker} — possible stock price contamination, "
                        f"falling back to entry price for current_price fallback"
                    )
                    exit_price = trade.entry_price
                else:
                    exit_price = trade.current_price or trade.entry_price

            # Sanity check: exit price shouldn't be vastly higher than entry (likely stock price)
            if exit_price > trade.entry_price * 5 and trade.entry_price > 0:
                logger.warning(
                    f"Exit price ${exit_price:.2f} is >5x entry ${trade.entry_price:.2f} "
                    f"for {trade.ticker} — possible stock price contamination, "
                    f"falling back to entry price"
                )
                exit_price = trade.entry_price

            trade.exit_price = exit_price
            trade.close_reason = 'MANUAL_CLOSE'

            direction_mult = 1 if trade.direction == 'BUY' else -1
            trade.realized_pnl = round(
                (trade.exit_price - trade.entry_price) * trade.qty * 100 * direction_mult,
                2,
            )

            trade.tradier_sl_order_id = None
            trade.tradier_tp_order_id = None

            # Lifecycle transition: OPEN → CLOSED (Point 11)
            lifecycle = self._get_lifecycle(db)
            lifecycle.transition(
                trade, TradeStatus.CLOSED,
                trigger='USER_MANUAL_CLOSE',
                metadata={'exit_price': trade.exit_price, 'pnl': trade.realized_pnl},
            )

            # Compute MFE/MAE from price history
            self._compute_mfe_mae(db, trade)

            db.commit()

            logger.info(
                f"Manual close: Trade {trade.id} ({trade.ticker}) at "
                f"${trade.exit_price:.2f}, P&L: ${trade.realized_pnl:+.2f}"
            )

            return {
                'id': trade.id,
                'ticker': trade.ticker,
                'exit_price': trade.exit_price,
                'realized_pnl': trade.realized_pnl,
                'status': trade.status,
            }

        except Exception as e:
            db.rollback()
            logger.exception(f"manual_close_position failed: {e}")
            raise
        finally:
            db.close()

    def adjust_bracket(self, trade_id, username, new_sl=None, new_tp=None):
        """Adjust SL or TP for an open trade.

        Point 4: Tradier doesn't support editing OCO orders.
        We must: cancel existing → place new OCO → update DB.

        Args:
            trade_id: PaperTrade.id
            username: Current user
            new_sl: New stop loss price (or None to keep current)
            new_tp: New take profit price (or None to keep current)

        Returns:
            Updated trade dict or None
        """
        from backend.database.paper_session import get_paper_db_with_user

        db = get_paper_db_with_user(username)
        try:
            trade = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.id == trade_id,
                    PaperTrade.status == TradeStatus.OPEN.value,
                )
                .first()
            )

            if not trade:
                return None

            # Update bracket prices
            if new_sl is not None:
                trade.sl_price = float(new_sl)
            if new_tp is not None:
                trade.tp_price = float(new_tp)

            # P0-6 FIX: Cancel+recreate OCO (Tradier doesn't support edit).
            # Emergency fallback: if recreate fails after cancel, log CRITICAL
            # so the position is flagged as unprotected.
            user_settings = db.get(UserSettings, username)
            if user_settings and trade.tradier_order_id:
                broker = None
                cancel_succeeded = False
                try:
                    broker = BrokerFactory.get_broker(user_settings)

                    # Step 1: Cancel existing bracket orders
                    if trade.tradier_sl_order_id:
                        broker.cancel_order(trade.tradier_sl_order_id)
                    if trade.tradier_tp_order_id:
                        broker.cancel_order(trade.tradier_tp_order_id)
                    cancel_succeeded = True

                    # Clear stale IDs immediately
                    trade.tradier_sl_order_id = None
                    trade.tradier_tp_order_id = None

                    # Step 2: Place new OCO if both SL and TP are set
                    if trade.sl_price and trade.tp_price:
                        occ_symbol = self._build_occ_symbol(trade)

                        # P0-6: Fixed dict keys to match place_oco_order() signature
                        oco = broker.place_oco_order(
                            sl_order={
                                'symbol': occ_symbol,
                                'quantity': trade.qty,
                                'stop': trade.sl_price,
                            },
                            tp_order={
                                'symbol': occ_symbol,
                                'quantity': trade.qty,
                                'price': trade.tp_price,
                            },
                        )

                        # Update order IDs from OCO response
                        legs = oco.get('leg', [])
                        if len(legs) >= 2:
                            trade.tradier_sl_order_id = str(legs[0].get('id', ''))
                            trade.tradier_tp_order_id = str(legs[1].get('id', ''))
                        else:
                            logger.warning(
                                f"OCO recreate returned unexpected legs: {oco}"
                            )

                except BrokerException as e:
                    if cancel_succeeded:
                        # CRITICAL: brackets were cancelled but recreate failed
                        # Position is now UNPROTECTED
                        logger.critical(
                            f"BRACKET GAP: Trade {trade_id} ({trade.ticker}) — "
                            f"old OCO cancelled but new OCO failed: {e}. "
                            f"Position is UNPROTECTED. Manual intervention required."
                        )
                    else:
                        logger.warning(
                            f"Broker error adjusting bracket for trade {trade_id}: {e}"
                        )
                except Exception as e:
                    if cancel_succeeded:
                        logger.critical(
                            f"BRACKET GAP: Trade {trade_id} ({trade.ticker}) — "
                            f"unexpected error after cancel: {e}. "
                            f"Position may be UNPROTECTED."
                        )
                    else:
                        logger.exception(
                            f"Unexpected error in bracket adjust for trade {trade_id}: {e}"
                        )

            trade.version += 1
            trade.updated_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Bracket adjusted: Trade {trade.id} ({trade.ticker}) — "
                f"SL=${trade.sl_price}, TP=${trade.tp_price}"
            )

            return {
                'id': trade.id,
                'ticker': trade.ticker,
                'sl_price': trade.sl_price,
                'tp_price': trade.tp_price,
                'version': trade.version,
            }

        except Exception as e:
            db.rollback()
            logger.exception(f"adjust_bracket failed: {e}")
            raise
        finally:
            db.close()

    # ─────────────────────────────────────────────────────────────
    # Job 4: Lifecycle Sync (every 60s) — Point 11
    # ─────────────────────────────────────────────────────────────

    def lifecycle_sync(self):
        """Check non-terminal trades and update their lifecycle states.

        Handles three transition types:
          1. PENDING → OPEN (order filled at broker)
          2. CLOSING → CLOSED (close order filled at broker)
          3. OPEN → EXPIRED (option expired worthless)

        Uses advisory lock (Point 10) to prevent overlapping executions.
        """
        if not is_market_open():
            return

        db = get_paper_db_system()
        if not self._acquire_advisory_lock(db, self.LOCK_ID_LIFECYCLE_SYNC):
            logger.debug("lifecycle_sync skipped — another instance holds the lock.")
            db.close()
            return

        lifecycle = self._get_lifecycle(db)

        try:
            # 1. PENDING trades → check broker for fill
            pending_trades = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.status == TradeStatus.PENDING.value,
                    PaperTrade.tradier_order_id.isnot(None),
                )
                .all()
            )

            for trade in pending_trades:
                try:
                    user_settings = db.get(UserSettings, trade.username)
                    if not user_settings:
                        continue

                    broker = BrokerFactory.get_broker(user_settings)
                    order = broker.get_order(trade.tradier_order_id)
                    status = (order.get('status') or '').lower()

                    if status == 'filled':
                        trade.entry_price = float(
                            order.get('avg_fill_price') or trade.entry_price
                        )
                        trade.broker_fill_price = trade.entry_price
                        trade.broker_fill_time = datetime.utcnow()
                        lifecycle.transition(
                            trade, TradeStatus.OPEN,
                            trigger='CRON_FILL_CHECK',
                            metadata={'fill_price': trade.entry_price},
                        )
                    elif status == 'partially_filled':
                        filled_qty = order.get('filled_quantity', trade.qty)
                        lifecycle.transition(
                            trade, TradeStatus.PARTIALLY_FILLED,
                            trigger='CRON_FILL_CHECK',
                            metadata={'filled_qty': filled_qty},
                        )
                    elif status in ('canceled', 'rejected'):
                        lifecycle.transition(
                            trade, TradeStatus.CANCELED,
                            trigger='CRON_FILL_CHECK',
                            metadata={'reason': order.get('reason', status)},
                        )
                except BrokerException as e:
                    logger.warning(
                        f"lifecycle_sync: broker error on PENDING trade {trade.id}: {e}"
                    )
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            # 2. CLOSING trades → check if close order filled
            closing_trades = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.status == TradeStatus.CLOSING.value,
                    PaperTrade.tradier_order_id.isnot(None),
                )
                .all()
            )

            for trade in closing_trades:
                try:
                    user_settings = db.query(UserSettings).filter_by(username=trade.username).first()
                    if not user_settings:
                        continue

                    broker = BrokerFactory.get_broker(user_settings)
                    order = broker.get_order(trade.tradier_order_id)
                    status = (order.get('status') or '').lower()

                    if status == 'filled':
                        trade.exit_price = float(
                            order.get('avg_fill_price') or trade.current_price or trade.entry_price
                        )
                        direction_mult = 1 if trade.direction == 'BUY' else -1
                        trade.realized_pnl = round(
                            (trade.exit_price - trade.entry_price) * trade.qty * 100 * direction_mult, 2
                        )
                        trade.close_reason = 'BROKER_FILL'
                        lifecycle.transition(
                            trade, TradeStatus.CLOSED,
                            trigger='CRON_CLOSE_FILL',
                            metadata={'fill_price': trade.exit_price},
                        )
                    elif status == 'rejected':
                        # Close order rejected — revert to OPEN
                        lifecycle.transition(
                            trade, TradeStatus.OPEN,
                            trigger='CRON_CLOSE_REJECTED',
                            metadata={'reason': order.get('reason', 'rejected')},
                        )
                except BrokerException as e:
                    logger.warning(
                        f"lifecycle_sync: broker error on CLOSING trade {trade.id}: {e}"
                    )
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            # 3. OPEN trades → check for expiration
            from datetime import date
            expired_trades = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.status == TradeStatus.OPEN.value,
                    PaperTrade.expiry <= date.today().isoformat(),
                )
                .all()
            )

            for trade in expired_trades:
                try:
                    # Check if current price is near zero (expired worthless)
                    if trade.current_price is not None and trade.current_price <= 0.05:
                        trade.exit_price = 0.0
                        trade.realized_pnl = -(trade.entry_price * trade.qty * 100)
                        trade.close_reason = 'EXPIRED'
                        lifecycle.transition(
                            trade, TradeStatus.EXPIRED,
                            trigger='CRON_EXPIRY_CHECK',
                            metadata={'last_price': trade.current_price},
                        )
                except InvalidTransitionError as e:
                    logger.warning(f"lifecycle_sync: invalid transition for trade {trade.id}: {e}")

            db.commit()
            logger.debug("lifecycle_sync completed successfully.")

        except Exception as e:
            db.rollback()
            logger.exception(f"lifecycle_sync failed: {e}")
        finally:
            self._release_advisory_lock(db, self.LOCK_ID_LIFECYCLE_SYNC)
            db.close()

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_occ_symbol(trade):
        """Build OCC option symbol from trade fields.

        Format: TICKER + YYMMDD + C/P + Strike*1000 (zero-padded 8 digits)
        Example: AAPL260320C00150000 = AAPL March 20, 2026 $150 Call
        """
        expiry_dt = datetime.strptime(trade.expiry, '%Y-%m-%d')
        opt_type = 'C' if trade.option_type.upper() == 'CALL' else 'P'
        strike_padded = f"{int(trade.strike * 1000):08d}"

        return (
            f"{trade.ticker}"
            f"{expiry_dt.strftime('%y%m%d')}"
            f"{opt_type}"
            f"{strike_padded}"
        )

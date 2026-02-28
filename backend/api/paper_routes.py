"""
Paper Trading API Routes
=========================
Phase 3, Step 3.4: REST endpoints for the Portfolio tab.

Blueprint: paper_bp (prefix: /api/paper)

All routes use RLS-aware sessions via get_paper_db_with_user().
Version checking (Point 8) is enforced on mutations.
"""

import logging
from datetime import datetime, date as date_type
from sqlalchemy import func
from dateutil import parser as dateutil_parser
from flask import Blueprint, jsonify, request, g, session

from backend.database.paper_models import (
    PaperTrade,
    PriceSnapshot,
    UserSettings,
    TradeStatus,
    StateTransition,
)
from backend.database.paper_session import get_paper_db_with_user, get_paper_db
from backend.services.monitor_service import MonitorService
from backend.services.lifecycle import LifecycleManager
from backend.services.broker.factory import BrokerFactory
from backend.services.broker.exceptions import BrokerException
from backend.services.context_service import ContextService
from backend.utils.market_hours import get_market_status

logger = logging.getLogger(__name__)
monitor = MonitorService()

paper_bp = Blueprint('paper', __name__, url_prefix='/api/paper')


# ─── Helpers ───────────────────────────────────────────────

def _get_username():
    """Get the current authenticated username.

    Reads from Flask session (set by security.login_user).
    Returns 401 if no session exists — no silent fallback to 'demo'.
    """
    # P0-10: Require authentication — abort(401) instead of falling back to 'demo'
    from flask import abort
    user = session.get('user')
    if not user:
        abort(401)
    return user


def _trade_to_dict(trade):
    """Convert a PaperTrade model to a JSON-serializable dict."""
    return {
        'id': trade.id,
        'ticker': trade.ticker,
        'option_type': trade.option_type,
        'strike': trade.strike,
        'expiry': trade.expiry,
        'direction': trade.direction,
        'entry_price': trade.entry_price,
        'qty': trade.qty,
        'sl_price': trade.sl_price,
        'tp_price': trade.tp_price,
        'strategy': trade.strategy,
        'card_score': trade.card_score,
        'ai_score': trade.ai_score,
        'ai_verdict': trade.ai_verdict,
        'gate_verdict': trade.gate_verdict,
        'technical_score': trade.technical_score,
        'sentiment_score': trade.sentiment_score,
        'delta_at_entry': trade.delta_at_entry,
        'iv_at_entry': trade.iv_at_entry,
        'current_price': trade.current_price,
        'unrealized_pnl': trade.unrealized_pnl,
        'status': trade.status,
        'exit_price': trade.exit_price,
        'realized_pnl': trade.realized_pnl,
        'close_reason': trade.close_reason,
        'trade_context': trade.trade_context or {},
        'broker_mode': trade.broker_mode,
        'tradier_order_id': trade.tradier_order_id,
        'version': trade.version,
        'created_at': trade.created_at.isoformat() if trade.created_at else None,
        'updated_at': trade.updated_at.isoformat() if trade.updated_at else None,
        'closed_at': trade.closed_at.isoformat() if trade.closed_at else None,
    }


def _snapshot_to_dict(snap):
    """Convert a PriceSnapshot model to a JSON-serializable dict."""
    return {
        'id': snap.id,
        'trade_id': snap.trade_id,
        'timestamp': snap.timestamp.isoformat() if snap.timestamp else None,
        'mark_price': snap.mark_price,
        'bid': snap.bid,
        'ask': snap.ask,
        'delta': snap.delta,
        'iv': snap.iv,
        'underlying': snap.underlying,
        'snapshot_type': snap.snapshot_type,
    }


def _normalize_expiry(raw):
    """Convert any date string to YYYY-MM-DD for the VARCHAR(10) expiry column.

    Handles: 'Feb 27, 2026', '2026-02-27', '2026-02-27T00:00:00', etc.
    Returns the original string if parsing fails (let DB validate).
    """
    if not raw:
        return raw
    raw = raw.strip()
    # Already in YYYY-MM-DD?
    if len(raw) == 10 and raw[4] == '-' and raw[7] == '-':
        return raw
    try:
        return dateutil_parser.parse(raw).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return raw


# ═══════════════════════════════════════════════════════════════
# 0. Health Check (no auth required — whitelisted in security.py)
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/health', endpoint='health_check')
def health_check():
    """Return service health. No auth required."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'version': '1.0',
    })


# ═══════════════════════════════════════════════════════════════
# 1. List Trades
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/trades', methods=['GET'])
def list_trades():
    """List trades with optional status filter.

    Query params:
      status: OPEN | CLOSED | EXPIRED | CANCELED | ALL (default: ALL)
      limit:  Max results (default: 100)
    """
    username = _get_username()
    status_filter = request.args.get('status', 'ALL').upper()
    limit = min(int(request.args.get('limit', 100)), 500)

    db = get_paper_db_with_user(username)
    try:
        query = db.query(PaperTrade).filter(PaperTrade.username == username)

        if status_filter == 'OPEN':
            query = query.filter(PaperTrade.status == TradeStatus.OPEN.value)
        elif status_filter == 'CLOSED':
            query = query.filter(PaperTrade.status == TradeStatus.CLOSED.value)
        elif status_filter == 'EXPIRED':
            query = query.filter(PaperTrade.status == TradeStatus.EXPIRED.value)
        elif status_filter == 'CANCELED':
            query = query.filter(PaperTrade.status == TradeStatus.CANCELED.value)
        # ALL = no filter

        trades = query.order_by(PaperTrade.created_at.desc()).limit(limit).all()

        # ── Inline price refresh for stale OPEN trades ──
        if status_filter == 'OPEN' and trades:
            stale = [t for t in trades if t.current_price is None
                     or t.current_price == t.entry_price]
            needs_greeks = [t for t in trades
                           if not t.delta_at_entry
                           or not (t.trade_context or {}).get('greeks')]
            refresh_set = list({t.id: t for t in (stale + needs_greeks)}.values())

            if refresh_set:
                try:
                    from backend.api.orats import OratsAPI
                    orats = OratsAPI()
                    for trade in refresh_set:
                        try:
                            quote = orats.get_option_quote(
                                trade.ticker,
                                trade.strike,
                                trade.expiry,
                                trade.option_type,
                            )
                            if not quote:
                                continue

                            if quote.get('mark') and (
                                trade.current_price is None
                                or trade.current_price == trade.entry_price
                            ):
                                trade.current_price = quote['mark']
                                direction = 1 if trade.direction == 'BUY' else -1
                                trade.unrealized_pnl = round(
                                    (quote['mark'] - trade.entry_price)
                                    * trade.qty * 100 * direction, 2
                                )

                            if quote.get('delta') or quote.get('theta'):
                                ctx = dict(trade.trade_context or {})
                                ctx['greeks'] = {
                                    'delta': quote.get('delta', 0),
                                    'gamma': quote.get('gamma', 0),
                                    'theta': quote.get('theta', 0),
                                    'vega': quote.get('vega', 0),
                                    'iv': quote.get('iv', 0),
                                }
                                ctx['volume'] = quote.get('volume', 0)
                                ctx['open_interest'] = quote.get('oi', 0)
                                trade.trade_context = ctx

                            if not trade.delta_at_entry and quote.get('delta'):
                                trade.delta_at_entry = quote['delta']
                            if not trade.iv_at_entry and quote.get('iv'):
                                trade.iv_at_entry = quote['iv']

                        except Exception:
                            pass
                    db.commit()
                except Exception as e:
                    logger.warning(f"Inline price refresh failed (non-fatal): {e}")

        return jsonify({
            'success': True,
            'trades': [_trade_to_dict(t) for t in trades],
            'count': len(trades),
            'market_status': get_market_status(),
        })

    except Exception as e:
        logger.exception(f"list_trades failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 2. Trade Detail (with price history)
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/trades/<int:trade_id>', methods=['GET'])
def get_trade(trade_id):
    """Get a single trade with its price snapshot history."""
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        trade = (
            db.query(PaperTrade)
            .filter(PaperTrade.id == trade_id, PaperTrade.username == username)
            .first()
        )

        if not trade:
            return jsonify({'success': False, 'error': 'Trade not found'}), 404

        snapshots = (
            db.query(PriceSnapshot)
            .filter(PriceSnapshot.trade_id == trade_id)
            .order_by(PriceSnapshot.timestamp.asc())
            .all()
        )

        result = _trade_to_dict(trade)
        result['price_history'] = [_snapshot_to_dict(s) for s in snapshots]

        return jsonify({'success': True, 'trade': result})

    except Exception as e:
        logger.exception(f"get_trade failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 3. Place New Paper Trade
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/trades', methods=['POST'])
def place_trade():
    """Place a new paper trade."""
    username = _get_username()
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'No JSON body provided'}), 400

    required = ['ticker', 'option_type', 'strike', 'expiry', 'entry_price']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({
            'success': False,
            'error': f'Missing required fields: {", ".join(missing)}'
        }), 400

    db = get_paper_db_with_user(username)
    try:
        if data.get('idempotency_key'):
            existing = (
                db.query(PaperTrade)
                .filter(PaperTrade.idempotency_key == data['idempotency_key'])
                .first()
            )
            if existing:
                return jsonify({
                    'success': True,
                    'trade': _trade_to_dict(existing),
                    'deduplicated': True,
                })

        user_settings = db.query(UserSettings).filter_by(username=username).first()
        if user_settings and user_settings.max_daily_trades:
            today_count = (
                db.query(func.count(PaperTrade.id))
                .filter(
                    PaperTrade.username == username,
                    func.date(PaperTrade.created_at) == date_type.today(),
                )
                .scalar()
            )
            if today_count >= user_settings.max_daily_trades:
                return jsonify({
                    'success': False,
                    'error': f'Daily trade limit reached ({user_settings.max_daily_trades})'
                }), 429

        if user_settings and user_settings.max_positions:
            open_count = (
                db.query(func.count(PaperTrade.id))
                .filter(
                    PaperTrade.username == username,
                    PaperTrade.status == TradeStatus.OPEN.value,
                )
                .scalar()
            )
            if open_count >= user_settings.max_positions:
                return jsonify({
                    'success': False,
                    'error': f'Max open positions reached ({user_settings.max_positions}). Close a position first.'
                }), 429

        if user_settings and user_settings.daily_loss_limit:
            todays_realized = (
                db.query(func.coalesce(func.sum(PaperTrade.realized_pnl), 0))
                .filter(
                    PaperTrade.username == username,
                    PaperTrade.status == TradeStatus.CLOSED.value,
                    func.date(PaperTrade.closed_at) == date_type.today(),
                )
                .scalar()
            )
            if todays_realized is not None and float(todays_realized) <= -abs(user_settings.daily_loss_limit):
                return jsonify({
                    'success': False,
                    'error': f'Daily loss limit breached (${abs(float(todays_realized)):.2f} lost today, limit: ${user_settings.daily_loss_limit:.2f})'
                }), 429

        # ── P1 BUG-E1: Server-side card_score + AI verdict gate enforcement ──
        card_score = data.get('card_score')
        ai_verdict = data.get('ai_verdict')

        if card_score is not None and float(card_score) < 40:
            return jsonify({
                'success': False,
                'error': 'Trade rejected: card score below minimum threshold'
            }), 400

        if ai_verdict and str(ai_verdict).upper() in ('AVOID', 'STRONG_AVOID'):
            return jsonify({
                'success': False,
                'error': 'Trade rejected: AI verdict is AVOID'
            }), 400

        # ── P3 BUG-E2: Recompute gate_verdict server-side ──
        if card_score is not None and float(card_score) < 40:
            server_gate_verdict = 'FAIL'
        elif ai_verdict and str(ai_verdict).upper() in ('AVOID', 'STRONG_AVOID'):
            server_gate_verdict = 'FAIL'
        elif card_score is not None and float(card_score) >= 70:
            server_gate_verdict = 'STRONG_PASS'
        elif card_score is not None and float(card_score) >= 40:
            server_gate_verdict = 'PASS'
        else:
            server_gate_verdict = data.get('gate_verdict', 'PASS')

        # ── P1 CRIT-3: Portfolio heat limit enforcement ──
        if user_settings and user_settings.heat_limit_pct and user_settings.account_balance:
            open_positions_for_heat = (
                db.query(PaperTrade)
                .filter(
                    PaperTrade.username == username,
                    PaperTrade.status == TradeStatus.OPEN.value,
                )
                .all()
            )
            current_heat_value = sum(
                t.entry_price * t.qty * 100 for t in open_positions_for_heat
            )
            proposed_cost = float(data['entry_price']) * int(data.get('qty', 1)) * 100
            total_heat_value = current_heat_value + proposed_cost
            heat_pct = (total_heat_value / user_settings.account_balance) * 100
            if heat_pct > user_settings.heat_limit_pct:
                return jsonify({
                    'success': False,
                    'error': (
                        f'Trade rejected: portfolio heat {heat_pct:.1f}% would exceed '
                        f'limit {user_settings.heat_limit_pct:.1f}%'
                    )
                }), 400

        trade = PaperTrade(
            username=username,
            ticker=data['ticker'].upper(),
            option_type=data['option_type'].upper(),
            strike=float(data['strike']),
            expiry=_normalize_expiry(data['expiry']),
            direction=data.get('direction', 'BUY').upper(),
            entry_price=float(data['entry_price']),
            qty=int(data.get('qty', 1)),
            sl_price=float(data['sl_price']) if data.get('sl_price') else None,
            tp_price=float(data['tp_price']) if data.get('tp_price') else None,
            strategy=data.get('strategy'),
            card_score=card_score,
            ai_score=data.get('ai_score'),
            ai_verdict=ai_verdict,
            gate_verdict=server_gate_verdict,
            technical_score=data.get('technical_score'),
            sentiment_score=data.get('sentiment_score'),
            delta_at_entry=data.get('delta_at_entry'),
            iv_at_entry=data.get('iv_at_entry'),
            idempotency_key=data.get('idempotency_key'),
            status=TradeStatus.PENDING.value,
        )

        db.add(trade)
        db.flush()

        try:
            from backend.api.orats import OratsAPI
            ctx_svc = ContextService(orats_api=OratsAPI())
            trade.trade_context = ctx_svc.capture_entry_context(
                ticker=trade.ticker,
                option_type=trade.option_type,
                strike=trade.strike,
                expiry=trade.expiry,
                entry_price=trade.entry_price,
            )
        except Exception as e:
            logger.warning(f'[place_trade] Context capture failed (non-fatal): {e}')

        lifecycle = LifecycleManager(db)
        lifecycle.transition(
            trade, TradeStatus.OPEN,
            trigger='USER_SUBMIT',
            metadata={
                'source': data.get('strategy', 'MANUAL'),
                'card_score': data.get('card_score'),
                'ai_score': data.get('ai_score'),
            },
        )

        broker_msg = None
        try:
            user_settings = db.query(UserSettings).filter_by(username=username).first()

            # ── P2 CRIT-4: Strict broker mode guard ──
            broker_ready = False
            if user_settings:
                _broker_mode = (user_settings.broker_mode or 'SANDBOX').upper()
                if 'LIVE' in _broker_mode:
                    if user_settings.tradier_live_token:
                        broker_ready = True
                    else:
                        logger.warning(
                            f"[place_trade] broker_mode={_broker_mode} but no live token — "
                            f"skipping broker order for {username}"
                        )
                        broker_msg = "Paper-only (LIVE mode selected but no live token configured)"
                else:
                    if user_settings.tradier_sandbox_token:
                        broker_ready = True
                    else:
                        broker_msg = "Paper-only (no sandbox token configured)"

            if user_settings and broker_ready:
                broker = BrokerFactory.get_broker(user_settings)
                occ = MonitorService._build_occ_symbol(trade)

                entry_order = broker.place_order({
                    'symbol': occ,
                    'underlying': trade.ticker,
                    'side': 'buy_to_open',
                    'quantity': trade.qty,
                    'type': 'limit',
                    'price': trade.entry_price,
                    'duration': 'day',
                })
                trade.tradier_order_id = str(entry_order)
                trade.broker_mode = (
                    'TRADIER_LIVE' if user_settings.broker_mode == 'TRADIER_LIVE'
                    else 'TRADIER_SANDBOX'
                )
                broker_msg = f"Tradier order {trade.tradier_order_id} placed"

                if trade.sl_price and trade.tp_price:
                    try:
                        oco = broker.place_oco_order(
                            sl_order={
                                'symbol': occ,
                                'side': 'sell_to_close',
                                'quantity': trade.qty,
                                'type': 'stop',
                                'stop': trade.sl_price,
                                'duration': 'gtc',
                            },
                            tp_order={
                                'symbol': occ,
                                'side': 'sell_to_close',
                                'quantity': trade.qty,
                                'type': 'limit',
                                'price': trade.tp_price,
                                'duration': 'gtc',
                            },
                        )
                        trade.tradier_sl_order_id = str(oco.get('sl_id', ''))
                        trade.tradier_tp_order_id = str(oco.get('tp_id', ''))
                        broker_msg += f" + OCO brackets attached"
                    except BrokerException as e:
                        logger.warning(f"OCO bracket placement failed: {e}")
                        broker_msg += f" (brackets failed: {e})"

        except BrokerException as e:
            db.rollback()
            logger.warning(f"Tradier order failed — trade rolled back: {e}")
            return jsonify({
                'success': False,
                'error': f'Broker rejected order: {e}',
                'broker_error': True,
            }), 502
        except Exception as e:
            logger.warning(f"Broker setup skipped: {e}")
            broker_msg = "Paper-only (no broker credentials)"

        db.commit()
        db.refresh(trade)

        logger.info(
            f"Paper trade placed: {trade.ticker} {trade.option_type} "
            f"${trade.strike} @ ${trade.entry_price} (#{trade.id})"
            f"{' — ' + broker_msg if broker_msg else ''}"
        )

        result = _trade_to_dict(trade)
        result['broker_msg'] = broker_msg

        return jsonify({
            'success': True,
            'trade': result,
        }), 201

    except Exception as e:
        db.rollback()
        logger.exception(f"place_trade failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 4. Close Position (Manual)
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/trades/<int:trade_id>/close', methods=['POST'])
def close_trade(trade_id):
    """Manually close an open position."""
    username = _get_username()
    data = request.get_json() or {}

    db = get_paper_db_with_user(username)
    try:
        trade = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.id == trade_id,
                PaperTrade.username == username,
                PaperTrade.status == TradeStatus.OPEN.value,
            )
            .first()
        )

        if not trade:
            return jsonify({'success': False, 'error': 'Trade not found or already closed'}), 404

        client_version = data.get('version')
        if client_version is not None and int(client_version) != trade.version:
            return jsonify({
                'success': False,
                'error': 'Trade was updated on another device. Refreshing...',
                'stale': True,
            }), 409

        db.close()

        result = monitor.manual_close_position(trade_id, username)

        if result:
            return jsonify({'success': True, 'trade': result})
        else:
            return jsonify({'success': False, 'error': 'Close failed'}), 500

    except Exception as e:
        db.close()
        logger.exception(f"close_trade failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 5. Adjust SL/TP
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/trades/<int:trade_id>/adjust', methods=['POST'])
def adjust_trade(trade_id):
    """Adjust stop loss or take profit for an open trade."""
    username = _get_username()
    data = request.get_json() or {}

    new_sl = data.get('new_sl')
    new_tp = data.get('new_tp')

    if new_sl is None and new_tp is None:
        return jsonify({
            'success': False,
            'error': 'Provide at least one of: new_sl, new_tp'
        }), 400

    try:
        result = monitor.adjust_bracket(
            trade_id=trade_id,
            username=username,
            new_sl=new_sl,
            new_tp=new_tp,
        )

        if result:
            return jsonify({'success': True, 'trade': result})
        else:
            return jsonify({'success': False, 'error': 'Trade not found or not open'}), 404

    except Exception as e:
        logger.exception(f"adjust_trade failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# 7. Portfolio Stats (Aggregate)
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get aggregate portfolio statistics for the stat cards."""
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        settings = db.get(UserSettings, username)
        account_balance = settings.account_balance if settings else 5000.0
        max_positions = settings.max_positions if settings else 5

        open_trades = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.username == username,
                PaperTrade.status == TradeStatus.OPEN.value,
            )
            .all()
        )

        closed_trades = (
            db.query(PaperTrade)
            .filter(
                PaperTrade.username == username,
                PaperTrade.status == TradeStatus.CLOSED.value,
            )
            .all()
        )

        total_unrealized = sum(t.unrealized_pnl or 0 for t in open_trades)
        total_invested = sum(t.entry_price * t.qty * 100 for t in open_trades)
        total_realized = sum(t.realized_pnl or 0 for t in closed_trades)

        wins = [t for t in closed_trades if (t.realized_pnl or 0) > 0]
        losses = [t for t in closed_trades if (t.realized_pnl or 0) < 0]
        win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0

        sorted_closed = sorted(
            closed_trades,
            key=lambda t: t.closed_at or datetime.min,
            reverse=True
        )
        consecutive_losses = 0
        for t in sorted_closed:
            if (t.realized_pnl or 0) < 0:
                consecutive_losses += 1
            else:
                break

        gross_profit = sum(t.realized_pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.realized_pnl for t in losses)) if losses else 0
        # P2 BUG-P5: Return 999.0 (perfect record) when there are no losses
        if gross_loss == 0:
            profit_factor = 999.0 if gross_profit > 0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

        portfolio_value = account_balance + total_unrealized + total_realized

        # P2 BUG-P3: todays_pnl filters only TODAY's trades
        today_utc = datetime.utcnow().date()
        todays_pnl = sum(
            (t.unrealized_pnl or 0)
            for t in open_trades
            if t.created_at and t.created_at.date() >= today_utc
        ) + sum(
            (t.realized_pnl or 0)
            for t in closed_trades
            if t.closed_at and t.closed_at.date() >= today_utc
        )

        cash_available = account_balance - total_invested + total_realized

        return jsonify({
            'success': True,
            'stats': {
                'portfolio_value': round(portfolio_value, 2),
                'todays_pnl': round(todays_pnl, 2),
                'open_positions': len(open_trades),
                'max_positions': max_positions,
                'cash_available': round(cash_available, 2),
                'total_pnl': round(total_realized + total_unrealized, 2),
                'total_realized': round(total_realized, 2),
                'total_unrealized': round(total_unrealized, 2),
                'win_rate': round(win_rate, 1),
                'profit_factor': round(profit_factor, 2),
                'total_trades': len(closed_trades),
                'wins': len(wins),
                'losses': len(losses),
                'consecutive_losses': consecutive_losses,
            },
            'market_status': get_market_status(),
        })

    except Exception as e:
        logger.exception(f"get_stats failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# 8. Market Status
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/market-status', methods=['GET'])
def market_status():
    """Get current market status."""
    return jsonify({
        'success': True,
        'market': get_market_status(),
    })


# ═══════════════════════════════════════════════════════════════
# 9. Analytics
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/analytics/summary', methods=['GET'])
def analytics_summary():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_summary(start_date=start, end_date=end)
        return jsonify({'success': True, 'summary': data})
    except Exception as e:
        logger.exception(f"analytics_summary failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/equity-curve', methods=['GET'])
def analytics_equity_curve():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_equity_curve(start_date=start, end_date=end)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception(f"analytics_equity_curve failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/drawdown', methods=['GET'])
def analytics_drawdown():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_max_drawdown(start_date=start, end_date=end)
        return jsonify({'success': True, 'drawdown': data})
    except Exception as e:
        logger.exception(f"analytics_drawdown failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/by-ticker', methods=['GET'])
def analytics_by_ticker():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_ticker_breakdown(start_date=start, end_date=end)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception(f"analytics_by_ticker failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/by-strategy', methods=['GET'])
def analytics_by_strategy():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_strategy_breakdown(start_date=start, end_date=end)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception(f"analytics_by_strategy failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/monthly', methods=['GET'])
def analytics_monthly():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_monthly_pnl(start_date=start, end_date=end)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception(f"analytics_monthly failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/mfe-mae', methods=['GET'])
def analytics_mfe_mae():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        start = request.args.get('start')
        end = request.args.get('end')
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        data = service.get_mfe_mae_analysis(start_date=start, end_date=end)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception(f"analytics_mfe_mae failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/export/csv', methods=['GET'])
def analytics_export_csv():
    import csv
    import io
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        trades = service.get_export_data()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID','Ticker','Type','Strike','Direction','Entry','Exit','Qty','P&L','Strategy','Status','Close Reason','Hold Time (hrs)','Opened','Closed'])
        for t in trades:
            writer.writerow([t.get('id',''),t.get('ticker',''),t.get('option_type',''),t.get('strike',''),t.get('direction',''),t.get('entry_price',''),t.get('exit_price',''),t.get('qty',''),t.get('realized_pnl',''),t.get('strategy',''),t.get('status',''),t.get('close_reason',''),t.get('hold_hours',''),t.get('opened_at',''),t.get('closed_at','')])
        from flask import Response
        return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment;filename=paper_trades.csv'})
    except Exception as e:
        logger.exception(f"analytics_export_csv failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/analytics/export/json', methods=['GET'])
def analytics_export_json():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        from backend.services.analytics_service import AnalyticsService
        service = AnalyticsService(db)
        trades = service.get_export_data()
        response = jsonify(trades)
        response.headers['Content-Disposition'] = 'attachment;filename=paper_trades.json'
        return response
    except Exception as e:
        logger.exception(f"analytics_export_json failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════

@paper_bp.route('/settings', methods=['GET'])
def settings_get():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        settings = db.query(UserSettings).filter_by(username=username).first()
        if not settings:
            return jsonify({'success': True, 'settings': {'max_positions': 5,'daily_loss_limit': 500.0,'account_balance': 5000.0,'default_sl_pct': 20.0,'default_tp_pct': 50.0,'max_daily_trades': 10,'theme': 'dark','alert_on_bracket_hit': True,'auto_close_expiry': True,'require_trade_confirm': True,'broker_mode': 'TRADIER_SANDBOX','tradier_account_id': None,'has_sandbox_token': False,'has_live_token': False}})
        return jsonify({'success': True, 'settings': {'max_positions': settings.max_positions,'daily_loss_limit': settings.daily_loss_limit,'account_balance': settings.account_balance,'default_sl_pct': settings.default_sl_pct,'default_tp_pct': settings.default_tp_pct,'max_daily_trades': settings.max_daily_trades,'theme': settings.theme,'alert_on_bracket_hit': settings.alert_on_bracket_hit,'auto_close_expiry': settings.auto_close_expiry,'require_trade_confirm': settings.require_trade_confirm,'broker_mode': settings.broker_mode,'tradier_account_id': settings.tradier_account_id,'has_sandbox_token': bool(settings.tradier_sandbox_token),'has_live_token': bool(settings.tradier_live_token)}})
    except Exception as e:
        logger.exception(f"settings_get failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/settings', methods=['PUT'])
def settings_update():
    username = _get_username()
    data = request.get_json() or {}
    db = get_paper_db_with_user(username)
    try:
        settings = db.query(UserSettings).filter_by(username=username).first()
        if not settings:
            settings = UserSettings(username=username)
            db.add(settings)
        if 'max_positions' in data: settings.max_positions = int(data['max_positions'])
        if 'daily_loss_limit' in data: settings.daily_loss_limit = float(data['daily_loss_limit'])
        if 'account_balance' in data: settings.account_balance = float(data['account_balance'])
        if 'default_sl_pct' in data: settings.default_sl_pct = float(data['default_sl_pct'])
        if 'default_tp_pct' in data: settings.default_tp_pct = float(data['default_tp_pct'])
        if 'max_daily_trades' in data: settings.max_daily_trades = int(data['max_daily_trades'])
        if 'theme' in data: settings.theme = data['theme']
        if 'alert_on_bracket_hit' in data: settings.alert_on_bracket_hit = bool(data['alert_on_bracket_hit'])
        if 'auto_close_expiry' in data: settings.auto_close_expiry = bool(data['auto_close_expiry'])
        if 'require_trade_confirm' in data: settings.require_trade_confirm = bool(data['require_trade_confirm'])
        if 'broker_mode' in data: settings.broker_mode = data['broker_mode']
        if data.get('tradier_account_id'): settings.tradier_account_id = data['tradier_account_id']
        if data.get('tradier_sandbox_token'):
            try:
                from backend.security.crypto import encrypt
                settings.tradier_sandbox_token = encrypt(data['tradier_sandbox_token'])
            except Exception:
                settings.tradier_sandbox_token = data['tradier_sandbox_token']
        if data.get('tradier_live_token'):
            try:
                from backend.security.crypto import encrypt
                settings.tradier_live_token = encrypt(data['tradier_live_token'])
            except Exception:
                settings.tradier_live_token = data['tradier_live_token']
        settings.updated_at = datetime.utcnow()
        _max = settings.max_positions
        _daily = settings.daily_loss_limit
        db.commit()
        logger.info(f"Settings updated for {username}: max_pos={_max}, daily_loss={_daily}")
        return jsonify({'success': True, 'message': 'Settings saved'})
    except Exception as e:
        db.rollback()
        logger.exception(f"settings_update failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()


@paper_bp.route('/settings/test-connection', methods=['GET'])
def settings_test_connection():
    username = _get_username()
    db = get_paper_db_with_user(username)
    try:
        settings = db.query(UserSettings).filter_by(username=username).first()
        if not settings or not (settings.tradier_sandbox_token or settings.tradier_live_token):
            return jsonify({'success': False, 'error': 'No broker credentials stored'})
        broker = BrokerFactory.get_broker(settings)
        result = broker.test_connection()
        return jsonify({'success': True, 'result': result})
    except BrokerException as e:
        return jsonify({'success': False, 'error': str(e)})
    except Exception as e:
        logger.exception(f"settings_test_connection failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        db.close()

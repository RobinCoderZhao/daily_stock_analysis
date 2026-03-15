# -*- coding: utf-8 -*-
"""Repository for strategy backtest signals and summaries."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage import (
    DatabaseManager,
    Signal,
    StrategyBacktestSignal,
    StrategyBacktestSummary,
)

logger = logging.getLogger(__name__)


class StrategyBacktestRepository:
    """Repository for strategy backtest data access."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def save_signals_batch(self, signals: List[Dict[str, Any]]) -> int:
        """Save a batch of strategy backtest signals. Returns count saved."""
        saved = 0
        with self.db.get_session() as session:
            for sig_dict in signals:
                # Check for duplicates
                existing = session.query(StrategyBacktestSignal).filter_by(
                    strategy_name=sig_dict.get("strategy_name"),
                    code=sig_dict.get("code"),
                    signal_date=sig_dict.get("signal_date"),
                ).first()
                if existing:
                    # Update evaluation results
                    for key in ("eval_status", "outcome", "return_pct", "exit_reason", "holding_days"):
                        if key in sig_dict and sig_dict[key] is not None:
                            setattr(existing, key, sig_dict[key])
                else:
                    record = StrategyBacktestSignal(**sig_dict)
                    session.add(record)
                saved += 1
            session.commit()
        return saved

    def get_signals(
        self,
        strategy_name: Optional[str] = None,
        code: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get strategy backtest signals with optional filters."""
        with self.db.get_session() as session:
            query = session.query(StrategyBacktestSignal)
            if strategy_name:
                query = query.filter(StrategyBacktestSignal.strategy_name == strategy_name)
            if code:
                query = query.filter(StrategyBacktestSignal.code == code)
            query = query.order_by(StrategyBacktestSignal.signal_date.desc()).limit(limit)
            return [
                {
                    "id": r.id,
                    "strategy_name": r.strategy_name,
                    "code": r.code,
                    "signal_date": r.signal_date.isoformat() if r.signal_date else None,
                    "direction": r.direction,
                    "entry_price": r.entry_price,
                    "stop_loss": r.stop_loss,
                    "take_profit": r.take_profit,
                    "eval_status": r.eval_status,
                    "outcome": r.outcome,
                    "return_pct": r.return_pct,
                    "exit_reason": r.exit_reason,
                    "holding_days": r.holding_days,
                }
                for r in query.all()
            ]

    def upsert_summary(self, summary_dict: Dict[str, Any]) -> None:
        """Insert or update a strategy backtest summary."""
        with self.db.get_session() as session:
            existing = session.query(StrategyBacktestSummary).filter_by(
                strategy_name=summary_dict["strategy_name"],
            ).first()
            if existing:
                for key, value in summary_dict.items():
                    if key != "id" and value is not None:
                        setattr(existing, key, value)
                existing.computed_at = datetime.now()
            else:
                record = StrategyBacktestSummary(**summary_dict)
                session.add(record)
            session.commit()

    def get_all_summaries(self) -> List[Dict[str, Any]]:
        """Get all strategy backtest summaries, ranked by win_rate_pct desc."""
        with self.db.get_session() as session:
            rows = (
                session.query(StrategyBacktestSummary)
                .order_by(StrategyBacktestSummary.win_rate_pct.desc().nullslast())
                .all()
            )
            return [
                {
                    "strategy_name": r.strategy_name,
                    "total_signals": r.total_signals,
                    "win_count": r.win_count,
                    "loss_count": r.loss_count,
                    "neutral_count": r.neutral_count,
                    "win_rate_pct": r.win_rate_pct,
                    "avg_return_pct": r.avg_return_pct,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "profit_factor": r.profit_factor,
                    "sharpe_ratio": r.sharpe_ratio,
                    "avg_holding_days": r.avg_holding_days,
                    "stop_loss_trigger_rate": r.stop_loss_trigger_rate,
                    "take_profit_trigger_rate": r.take_profit_trigger_rate,
                    "computed_confidence": r.computed_confidence,
                    "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                }
                for r in rows
            ]

    def get_summary(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Get one strategy backtest summary."""
        summaries = self.get_all_summaries()
        for s in summaries:
            if s["strategy_name"] == strategy_name:
                return s
        return None


class SignalRepository:
    """Repository for live signal tracking."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def create_signal(self, signal_dict: Dict[str, Any]) -> int:
        """Create a new signal record. Returns the signal ID."""
        with self.db.get_session() as session:
            record = Signal(**signal_dict)
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.id

    def get_active_signals(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """Get paginated active signals."""
        with self.db.get_session() as session:
            base_query = session.query(Signal).filter(
                Signal.status.in_(["pending", "active"]),
            )
            total = base_query.count()
            items = (
                base_query
                .order_by(Signal.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )
            return {
                "total": total,
                "page": page,
                "limit": limit,
                "items": [self._to_dict(s) for s in items],
            }

    def get_all_signals(
        self,
        status: Optional[str] = None,
        code: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Get paginated signals with optional filters."""
        with self.db.get_session() as session:
            query = session.query(Signal)
            if status:
                query = query.filter(Signal.status == status)
            if code:
                query = query.filter(Signal.code == code)
            total = query.count()
            items = (
                query
                .order_by(Signal.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )
            return {
                "total": total,
                "page": page,
                "limit": limit,
                "items": [self._to_dict(s) for s in items],
            }

    def get_signal_by_id(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """Get a single signal by ID."""
        with self.db.get_session() as session:
            s = session.query(Signal).filter_by(id=signal_id).first()
            return self._to_dict(s) if s else None

    def update_signal(self, signal_id: int, updates: Dict[str, Any]) -> bool:
        """Update a signal record."""
        with self.db.get_session() as session:
            s = session.query(Signal).filter_by(id=signal_id).first()
            if not s:
                return False
            for key, value in updates.items():
                if hasattr(s, key):
                    setattr(s, key, value)
            session.commit()
            return True

    def get_active_signals_list(self) -> List[Dict[str, Any]]:
        """Get all active signals as a flat list (for risk checks)."""
        with self.db.get_session() as session:
            items = (
                session.query(Signal)
                .filter(Signal.status.in_(["pending", "active"]))
                .all()
            )
            return [self._to_dict(s) for s in items]

    def get_signal_summary(self) -> Dict[str, Any]:
        """Get aggregated signal performance summary."""
        with self.db.get_session() as session:
            all_signals = session.query(Signal).all()
            active = [s for s in all_signals if s.status in ("pending", "active")]
            closed = [s for s in all_signals if s.status not in ("pending", "active", "cancelled")]

            wins = [s for s in closed if s.return_pct is not None and s.return_pct > 0]
            losses = [s for s in closed if s.return_pct is not None and s.return_pct < 0]

            returns = [s.return_pct for s in closed if s.return_pct is not None]
            avg_return = sum(returns) / len(returns) if returns else None

            return {
                "total_signals": len(all_signals),
                "active_count": len(active),
                "closed_count": len(closed),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate_pct": (
                    round(len(wins) / len(closed) * 100, 2)
                    if closed else None
                ),
                "avg_return_pct": round(avg_return, 4) if avg_return is not None else None,
            }

    @staticmethod
    def _to_dict(s: Signal) -> Dict[str, Any]:
        return {
            "id": s.id,
            "analysis_history_id": s.analysis_history_id,
            "code": s.code,
            "stock_name": s.stock_name,
            "strategy_name": s.strategy_name,
            "direction": s.direction,
            "entry_price": s.entry_price,
            "stop_loss": s.stop_loss,
            "take_profit": s.take_profit,
            "position_pct": s.position_pct,
            "confidence": s.confidence,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
            "current_price": s.current_price,
            "return_pct": s.return_pct,
            "holding_days": s.holding_days,
            "expire_date": s.expire_date.isoformat() if s.expire_date else None,
        }

# -*- coding: utf-8 -*-
"""
===================================
分析服务层
===================================

职责：
1. 封装股票分析逻辑
2. 调用 analyzer 和 pipeline 执行分析
3. 保存分析结果到数据库
"""

import logging
import uuid
from typing import Optional, Dict, Any

from src.repositories.analysis_repo import AnalysisRepository

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    分析服务
    
    封装股票分析相关的业务逻辑
    """
    
    def __init__(self):
        """初始化分析服务"""
        self.repo = AnalysisRepository()
    
    def analyze_stock(
        self,
        stock_code: str,
        report_type: str = "detailed",
        force_refresh: bool = False,
        query_id: Optional[str] = None,
        send_notification: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        执行股票分析
        
        Args:
            stock_code: 股票代码
            report_type: 报告类型 (simple/detailed)
            force_refresh: 是否强制刷新
            query_id: 查询 ID（可选）
            send_notification: 是否发送通知（API 触发默认发送）
            
        Returns:
            分析结果字典，包含:
            - stock_code: 股票代码
            - stock_name: 股票名称
            - report: 分析报告
        """
        try:
            # 导入分析相关模块
            from src.config import get_config
            from src.core.pipeline import StockAnalysisPipeline
            from src.enums import ReportType
            
            # 生成 query_id
            if query_id is None:
                query_id = uuid.uuid4().hex
            
            # 获取配置
            config = get_config()
            
            # 创建分析流水线
            pipeline = StockAnalysisPipeline(
                config=config,
                query_id=query_id,
                query_source="api"
            )
            
            # 确定报告类型 (API: simple/detailed/brief -> ReportType)
            if report_type == "detailed":
                rt = ReportType.FULL
            elif report_type == "brief":
                rt = ReportType.BRIEF
            else:
                rt = ReportType.SIMPLE
            
            # 执行分析
            result = pipeline.process_single_stock(
                code=stock_code,
                skip_analysis=False,
                single_stock_notify=send_notification,
                report_type=rt
            )
            
            if result is None:
                logger.warning(f"分析股票 {stock_code} 返回空结果")
                return None
            
            # 构建响应
            return self._build_analysis_response(result, query_id)
            
        except Exception as e:
            logger.error(f"分析股票 {stock_code} 失败: {e}", exc_info=True)
            return None
    
    def _build_analysis_response(
        self, 
        result: Any, 
        query_id: str
    ) -> Dict[str, Any]:
        """
        构建分析响应
        
        Args:
            result: AnalysisResult 对象
            query_id: 查询 ID
            
        Returns:
            格式化的响应字典
        """
        # 获取狙击点位
        sniper_points = {}
        if hasattr(result, 'get_sniper_points'):
            sniper_points = result.get_sniper_points() or {}
        
        # 计算情绪标签
        sentiment_label = self._get_sentiment_label(result.sentiment_score)

        # Phase 2: Compute multi-factor composite score
        composite_score_data = self._compute_composite_score(result)
        
        # 构建报告结构
        report = {
            "meta": {
                "query_id": query_id,
                "stock_code": result.code,
                "stock_name": result.name,
                "report_type": "detailed",
                "current_price": result.current_price,
                "change_pct": result.change_pct,
                "model_used": getattr(result, "model_used", None),
            },
            "summary": {
                "analysis_summary": result.analysis_summary,
                "operation_advice": result.operation_advice,
                "trend_prediction": result.trend_prediction,
                "sentiment_score": result.sentiment_score,
                "sentiment_label": sentiment_label,
            },
            "strategy": {
                "ideal_buy": sniper_points.get("ideal_buy"),
                "secondary_buy": sniper_points.get("secondary_buy"),
                "stop_loss": sniper_points.get("stop_loss"),
                "take_profit": sniper_points.get("take_profit"),
            },
            "composite_score": composite_score_data,
            "details": {
                "news_summary": result.news_summary,
                "technical_analysis": result.technical_analysis,
                "fundamental_analysis": result.fundamental_analysis,
                "risk_warning": result.risk_warning,
            }
        }
        
        return {
            "stock_code": result.code,
            "stock_name": result.name,
            "report": report,
        }

    def _compute_composite_score(self, result: Any) -> Optional[Dict[str, Any]]:
        """Compute multi-factor composite score from analysis result.

        Returns dict with score breakdown, or None if scoring unavailable.
        """
        try:
            from src.core.multi_factor_scorer import MultiFactorScorer
            from src.core.confidence_engine import ConfidenceEngine

            # Get trend_result if available
            trend_result = getattr(result, 'trend_result', None)

            # Determine market regime from context
            market_regime = "均衡"  # default
            context = getattr(result, 'context_snapshot', None)
            if context and isinstance(context, dict):
                regime = context.get('market_regime')
                if regime in ("进攻", "均衡", "防守"):
                    market_regime = regime

            # Compute multi-factor score
            scorer = MultiFactorScorer()
            scores = scorer.score(
                trend_result=trend_result,
                fundamental_data=None,   # future: Tushare data
                money_flow_data=None,    # future: Tushare data
                market_regime=market_regime,
            )

            # Compute confidence
            engine = ConfidenceEngine(db=None)
            strategy_name = getattr(result, 'strategy_name', '') or ''
            confidence = engine.compute(
                strategy_name=strategy_name,
                code=result.code,
                market_regime=market_regime,
            )

            return {
                "total": scores.total,
                "label": scores.label,
                "technical": scores.technical,
                "fundamental": scores.fundamental,
                "money_flow": scores.money_flow,
                "market": scores.market,
                "confidence": confidence.final_score,
            }
        except Exception as exc:
            logger.debug("Composite score computation skipped: %s", exc)
            return None
    
    def _get_sentiment_label(self, score: int) -> str:
        """
        根据评分获取情绪标签
        
        Args:
            score: 情绪评分 (0-100)
            
        Returns:
            情绪标签
        """
        if score >= 80:
            return "极度乐观"
        elif score >= 60:
            return "乐观"
        elif score >= 40:
            return "中性"
        elif score >= 20:
            return "悲观"
        else:
            return "极度悲观"

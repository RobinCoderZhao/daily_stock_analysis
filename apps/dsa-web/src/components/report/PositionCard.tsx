import type React from 'react';
import type { PositionAdvice as PositionAdviceType, ReportStrategy as ReportStrategyType } from '../../types/analysis';
import { Card } from '../common';

interface PositionCardProps {
  positionAdvice?: PositionAdviceType;
  strategy?: ReportStrategyType;
}

/**
 * Position advice card showing sizing recommendation alongside strategy points.
 */
export const PositionCard: React.FC<PositionCardProps> = ({
  positionAdvice,
  strategy,
}) => {
  if (!strategy && !positionAdvice) return null;

  const strategyItems = strategy ? [
    { label: '理想买入', value: strategy.idealBuy, color: '#00ff88' },
    { label: '二次买入', value: strategy.secondaryBuy, color: '#00d4ff' },
    { label: '止损价位', value: strategy.stopLoss, color: '#ff4466' },
    { label: '止盈目标', value: strategy.takeProfit, color: '#ffaa00' },
  ] : [];

  return (
    <Card variant="bordered" padding="md">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="label-uppercase">STRATEGY POINTS</span>
        <h3 className="text-base font-semibold text-white">狙击点位</h3>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {strategyItems.map((item) => (
          <div
            key={item.label}
            className="relative overflow-hidden rounded-lg bg-elevated border border-white/5 p-3 hover:border-white/10 transition-colors"
          >
            <div className="flex flex-col">
              <span className="text-xs text-muted mb-0.5">{item.label}</span>
              <span
                className="text-lg font-bold font-mono"
                style={{ color: item.value ? item.color : 'var(--text-muted)' }}
              >
                {item.value || '—'}
              </span>
            </div>
            <div
              className="absolute bottom-0 left-0 right-0 h-0.5"
              style={{ background: `linear-gradient(90deg, ${item.color}00, ${item.color}, ${item.color}00)` }}
            />
          </div>
        ))}
      </div>

      {/* Position advice section */}
      {positionAdvice && (
        <div className="mt-4 pt-3 border-t border-white/5">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="label-uppercase">POSITION SIZING</span>
            <h4 className="text-sm font-semibold text-white">仓位建议</h4>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {/* Position % */}
            <div className="rounded-lg bg-elevated border border-white/5 p-3">
              <span className="text-xs text-muted block mb-1">建议仓位</span>
              <div className="flex items-baseline gap-1">
                <span className="text-xl font-bold font-mono text-cyan">
                  {positionAdvice.positionPct.toFixed(1)}
                </span>
                <span className="text-xs text-muted">%</span>
              </div>
              {/* Mini bar */}
              <div className="mt-1.5 h-1 rounded-full bg-white/5 overflow-hidden">
                <div
                  className="h-full rounded-full bg-cyan transition-all duration-500"
                  style={{
                    width: `${Math.min(positionAdvice.positionPct / 20 * 100, 100)}%`,
                    boxShadow: '0 0 6px rgba(0, 212, 255, 0.4)',
                  }}
                />
              </div>
            </div>

            {/* Profit/Loss ratio */}
            <div className="rounded-lg bg-elevated border border-white/5 p-3">
              <span className="text-xs text-muted block mb-1">盈亏比</span>
              <span className="text-xl font-bold font-mono text-success">
                {positionAdvice.profitLossRatio}
              </span>
            </div>

            {/* Confidence */}
            <div className="rounded-lg bg-elevated border border-white/5 p-3">
              <span className="text-xs text-muted block mb-1">信号置信度</span>
              <div className="flex items-baseline gap-1">
                <span className="text-xl font-bold font-mono text-purple-400">
                  {positionAdvice.confidence.toFixed(0)}
                </span>
                <span className="text-xs text-muted">/ 100</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
};

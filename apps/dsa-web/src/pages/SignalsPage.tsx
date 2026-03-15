import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { signalsApi } from '../api/signals';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, Badge, Pagination } from '../components/common';
import type {
  SignalItem,
  SignalSummary,
  StrategyPerformanceItem,
} from '../types/signals';

// ============ Helpers ============

function pct(value?: number | null): string {
  if (value == null) return '--';
  return `${value.toFixed(2)}%`;
}

function pctColor(value?: number | null): string {
  if (value == null) return 'text-secondary';
  if (value > 0) return 'text-emerald-400';
  if (value < 0) return 'text-red-400';
  return 'text-secondary';
}

function statusBadge(status: string) {
  switch (status) {
    case 'active':
      return <Badge variant="success" glow>活跃</Badge>;
    case 'pending':
      return <Badge variant="warning">待激活</Badge>;
    case 'closed_tp':
      return <Badge variant="success">止盈</Badge>;
    case 'closed_sl':
      return <Badge variant="danger">止损</Badge>;
    case 'expired':
      return <Badge variant="default">过期</Badge>;
    case 'cancelled':
      return <Badge variant="default">取消</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
}

function directionBadge(direction: string) {
  switch (direction) {
    case 'long':
      return <Badge variant="success">做多</Badge>;
    case 'cash':
      return <Badge variant="warning">持币</Badge>;
    default:
      return <Badge variant="default">{direction}</Badge>;
  }
}


// ============ Summary Cards ============


const SummaryCards: React.FC<{ summary: SignalSummary | null; loading: boolean }> = ({ summary, loading }) => {
  if (loading || !summary) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i} className="p-4 animate-pulse">
            <div className="h-3 bg-white/10 rounded w-16 mb-2" />
            <div className="h-6 bg-white/10 rounded w-12" />
          </Card>
        ))}
      </div>
    );
  }

  const cards = [
    { label: '活跃信号', value: String(summary.activeCount), accent: true },
    { label: '胜率', value: summary.winRatePct != null ? `${summary.winRatePct.toFixed(1)}%` : '--', accent: false },
    { label: '胜/负', value: `${summary.winCount}/${summary.lossCount}`, accent: false },
    { label: '平均收益', value: summary.avgReturnPct != null ? `${summary.avgReturnPct.toFixed(2)}%` : '--', accent: false },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((c) => (
        <Card key={c.label} className="p-4">
          <div className="text-xs text-secondary mb-1">{c.label}</div>
          <div className={`text-xl font-mono font-bold ${c.accent ? 'text-cyan' : 'text-white'}`}>{c.value}</div>
        </Card>
      ))}
    </div>
  );
};

// ============ Active Signals Table ============

const SignalTable: React.FC<{
  signals: SignalItem[];
  loading: boolean;
  onClose: (id: number) => void;
}> = ({ signals, loading, onClose }) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-6 h-6 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
      </div>
    );
  }

  if (!signals.length) {
    return (
      <div className="flex items-center justify-center py-16 text-secondary text-sm">
        暂无信号数据
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10">
            <th className="text-left text-xs text-secondary font-medium py-3 px-3">股票</th>
            <th className="text-left text-xs text-secondary font-medium py-3 px-2">策略</th>
            <th className="text-center text-xs text-secondary font-medium py-3 px-2">方向</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">入场价</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">现价</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">收益</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">止损</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">止盈</th>
            <th className="text-center text-xs text-secondary font-medium py-3 px-2">状态</th>
            <th className="text-center text-xs text-secondary font-medium py-3 px-2">创建</th>
            <th className="text-center text-xs text-secondary font-medium py-3 px-2">操作</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((sig) => (
            <tr key={sig.id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
              <td className="py-2.5 px-3">
                <div className="font-mono text-white">{sig.code}</div>
                {sig.stockName && <div className="text-xs text-secondary">{sig.stockName}</div>}
              </td>
              <td className="py-2.5 px-2 text-xs text-secondary">{sig.strategyName || '--'}</td>
              <td className="py-2.5 px-2 text-center">{directionBadge(sig.direction)}</td>
              <td className="py-2.5 px-2 text-right font-mono">{sig.entryPrice?.toFixed(2) || '--'}</td>
              <td className="py-2.5 px-2 text-right font-mono">{sig.currentPrice?.toFixed(2) || '--'}</td>
              <td className={`py-2.5 px-2 text-right font-mono font-semibold ${pctColor(sig.returnPct)}`}>
                {pct(sig.returnPct)}
              </td>
              <td className="py-2.5 px-2 text-right font-mono text-red-400/60">{sig.stopLoss?.toFixed(2) || '--'}</td>
              <td className="py-2.5 px-2 text-right font-mono text-emerald-400/60">{sig.takeProfit?.toFixed(2) || '--'}</td>
              <td className="py-2.5 px-2 text-center">{statusBadge(sig.status)}</td>
              <td className="py-2.5 px-2 text-center text-xs text-secondary">
                {sig.createdAt ? new Date(sig.createdAt).toLocaleDateString('zh-CN') : '--'}
              </td>
              <td className="py-2.5 px-2 text-center">
                {['active', 'pending'].includes(sig.status) ? (
                  <button
                    type="button"
                    className="text-xs text-red-400 hover:text-red-300 transition-colors"
                    onClick={() => onClose(sig.id)}
                  >
                    关闭
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ============ Strategy Ranking ============

const StrategyRankingTable: React.FC<{
  strategies: StrategyPerformanceItem[];
  loading: boolean;
}> = ({ strategies, loading }) => {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-6 h-6 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
      </div>
    );
  }

  if (!strategies.length) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <span className="text-secondary text-sm">暂无策略回测数据</span>
        <span className="text-xs text-secondary/60">启动策略回测后数据将展示在此处</span>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10">
            <th className="text-left text-xs text-secondary font-medium py-3 px-3">#</th>
            <th className="text-left text-xs text-secondary font-medium py-3 px-2">策略</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">信号数</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">胜率</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">平均收益</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">盈亏比</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">夏普</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">最大回撤</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">平均持仓</th>
            <th className="text-right text-xs text-secondary font-medium py-3 px-2">止损率</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s, idx) => {
            const winRateColor = (s.winRatePct ?? 0) > 50 ? 'text-emerald-400' : (s.winRatePct ?? 0) < 40 ? 'text-red-400' : 'text-amber-400';
            return (
              <tr key={s.strategyName} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="py-2.5 px-3 font-mono text-secondary">{idx + 1}</td>
                <td className="py-2.5 px-2">
                  <span className="text-white font-medium">{s.strategyName}</span>
                </td>
                <td className="py-2.5 px-2 text-right font-mono">{s.totalSignals}</td>
                <td className={`py-2.5 px-2 text-right font-mono font-semibold ${winRateColor}`}>
                  {pct(s.winRatePct)}
                </td>
                <td className={`py-2.5 px-2 text-right font-mono ${pctColor(s.avgReturnPct)}`}>
                  {pct(s.avgReturnPct)}
                </td>
                <td className="py-2.5 px-2 text-right font-mono">{s.profitFactor?.toFixed(2) || '--'}</td>
                <td className="py-2.5 px-2 text-right font-mono">{s.sharpeRatio?.toFixed(2) || '--'}</td>
                <td className="py-2.5 px-2 text-right font-mono text-red-400/70">
                  {s.maxDrawdownPct != null ? `${s.maxDrawdownPct.toFixed(2)}%` : '--'}
                </td>
                <td className="py-2.5 px-2 text-right font-mono">{s.avgHoldingDays?.toFixed(1) || '--'}天</td>
                <td className="py-2.5 px-2 text-right font-mono">
                  {s.stopLossTriggerRate != null ? `${(s.stopLossTriggerRate * 100).toFixed(1)}%` : '--'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ============ Main Page ============

type TabKey = 'active' | 'ranking' | 'history';

const SignalsPage: React.FC = () => {
  // Tab
  const [activeTab, setActiveTab] = useState<TabKey>('active');

  // Summary
  const [summary, setSummary] = useState<SignalSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  // Signals list
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(true);
  const [signalsTotal, setSignalsTotal] = useState(0);
  const [signalsPage, setSignalsPage] = useState(1);
  const signalsLimit = 20;

  // Strategy ranking
  const [strategies, setStrategies] = useState<StrategyPerformanceItem[]>([]);
  const [strategiesLoading, setStrategiesLoading] = useState(false);

  // Strategy backtest running
  const [backtestRunning, setBacktestRunning] = useState(false);

  // Error
  const [error, setError] = useState<ParsedApiError | null>(null);

  // Fetch summary
  const fetchSummary = useCallback(async () => {
    setSummaryLoading(true);
    try {
      const data = await signalsApi.getSummary();
      setSummary(data);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  // Fetch signals
  const fetchSignals = useCallback(async (tab: TabKey, page: number) => {
    setSignalsLoading(true);
    try {
      const statusFilter = tab === 'active' ? 'active' : undefined;
      const data = await signalsApi.getSignals({
        status: statusFilter,
        page,
        limit: signalsLimit,
      });
      setSignals(data.items);
      setSignalsTotal(data.total);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setSignalsLoading(false);
    }
  }, []);

  // Fetch strategy ranking
  const fetchRanking = useCallback(async () => {
    setStrategiesLoading(true);
    try {
      const data = await signalsApi.getStrategyRanking();
      setStrategies(data.strategies);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setStrategiesLoading(false);
    }
  }, []);

  // Close signal
  const handleCloseSignal = useCallback(async (id: number) => {
    try {
      await signalsApi.closeSignal(id);
      // Refresh
      await fetchSignals(activeTab, signalsPage);
      await fetchSummary();
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, [activeTab, signalsPage, fetchSignals, fetchSummary]);

  // Run strategy backtest
  const handleRunBacktest = useCallback(async () => {
    setBacktestRunning(true);
    setError(null);
    try {
      await signalsApi.runStrategyBacktest({});
      await fetchRanking();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setBacktestRunning(false);
    }
  }, [fetchRanking]);

  // Initial load
  useEffect(() => {
    void fetchSummary();
  }, [fetchSummary]);

  // Load tab data
  useEffect(() => {
    if (activeTab === 'ranking') {
      void fetchRanking();
    } else {
      void fetchSignals(activeTab, signalsPage);
    }
  }, [activeTab, signalsPage, fetchSignals, fetchRanking]);

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'active', label: '活跃信号' },
    { key: 'ranking', label: '策略排行' },
    { key: 'history', label: '历史信号' },
  ];

  return (
    <div className="min-h-screen p-6 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">信号跟踪</h1>
          <p className="text-sm text-secondary mt-1">实时交易信号 · 策略回测排行</p>
        </div>
        <button
            type="button"
            className="btn-primary text-sm"
            disabled={backtestRunning}
            onClick={handleRunBacktest}
          >
            {backtestRunning ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                回测中…
              </span>
            ) : (
              '启动策略回测'
            )}
          </button>
      </div>

      {/* Error */}
      {error && (
        <ApiErrorAlert error={error} />
      )}

      {/* Summary cards */}
      <SummaryCards summary={summary} loading={summaryLoading} />

      {/* Tabs */}
      <Card className="overflow-hidden">
        <div className="flex border-b border-white/10">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`px-5 py-3 text-sm font-medium transition-colors relative ${
                activeTab === tab.key
                  ? 'text-cyan'
                  : 'text-secondary hover:text-white'
              }`}
              onClick={() => {
                setActiveTab(tab.key);
                setSignalsPage(1);
              }}
            >
              {tab.label}
              {activeTab === tab.key && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan" />
              )}
            </button>
          ))}
        </div>

        <div className="p-0">
          {activeTab === 'ranking' ? (
            <StrategyRankingTable strategies={strategies} loading={strategiesLoading} />
          ) : (
            <>
              <SignalTable
                signals={signals}
                loading={signalsLoading}
                onClose={handleCloseSignal}
              />
              {signalsTotal > signalsLimit && (
                <div className="flex justify-center py-4 border-t border-white/5">
                  <Pagination
                    currentPage={signalsPage}
                    totalPages={Math.ceil(signalsTotal / signalsLimit)}
                    onPageChange={setSignalsPage}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  );
};

export default SignalsPage;

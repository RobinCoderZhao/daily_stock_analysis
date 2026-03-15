import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { watchlistApi, type EnrichedWatchlistItem } from '../api/watchlist';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert } from '../components/common';
import { validateStockCode } from '../utils/validation';

/* ─── Score color helpers ─── */
function scoreColor(score: number | null): string {
  if (score === null || score === undefined) return 'text-muted';
  if (score >= 80) return 'text-emerald-400';
  if (score >= 60) return 'text-cyan';
  if (score >= 40) return 'text-amber-400';
  return 'text-red-400';
}

function scoreBg(score: number | null): string {
  if (score === null || score === undefined) return 'bg-elevated';
  if (score >= 80) return 'bg-emerald-500/20';
  if (score >= 60) return 'bg-cyan/20';
  if (score >= 40) return 'bg-amber-500/20';
  return 'bg-red-500/20';
}

function barColor(score: number | null): string {
  if (score === null || score === undefined) return 'bg-white/10';
  if (score >= 80) return 'bg-emerald-400';
  if (score >= 60) return 'bg-cyan';
  if (score >= 40) return 'bg-amber-400';
  return 'bg-red-400';
}

function formatDate(iso: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${m}/${day} ${h}:${min}`;
}

/* ─── Score Bar Component ─── */
const ScoreBar: React.FC<{ label: string; score: number | null; max: number }> = ({ label, score, max }) => (
  <div className="flex items-center gap-2 text-xs">
    <span className="w-14 text-secondary shrink-0">{label}</span>
    <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-500 ${barColor(score)}`}
        style={{ width: score !== null ? `${(score / max) * 100}%` : '0%' }}
      />
    </div>
    <span className={`w-10 text-right tabular-nums ${scoreColor(score)}`}>
      {score !== null ? `${Math.round(score)}` : '--'}/{max}
    </span>
  </div>
);

/* ─── Stock Card ─── */
const StockCard: React.FC<{
  item: EnrichedWatchlistItem;
  isActive: boolean;
  onClick: () => void;
  onRemove: () => void;
  onAnalyze: () => void;
}> = ({ item, isActive, onClick, onRemove, onAnalyze }) => {
  const score = item.composite_score ?? item.sentiment_score;
  return (
    <div
      className={`group relative rounded-2xl border p-4 backdrop-blur-sm cursor-pointer transition-all duration-200
        ${isActive
          ? 'border-cyan/40 bg-cyan/5 ring-1 ring-cyan/20'
          : 'border-white/8 bg-card/60 hover:border-white/16 hover:bg-card/80'
        }`}
      onClick={onClick}
    >
      {/* Left accent bar */}
      <div className={`absolute left-0 top-3 bottom-3 w-1 rounded-full ${barColor(score)}`} />

      <div className="flex items-start justify-between pl-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white truncate">
              {item.name || item.code}
            </h3>
            {score !== null && (
              <span className={`shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-lg text-sm font-bold ${scoreBg(score)} ${scoreColor(score)}`}>
                {Math.round(score)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-1 text-xs text-muted">
            <span className="font-mono">{item.code}</span>
            {item.analysis_date && (
              <>
                <span className="text-white/20">·</span>
                <span>{formatDate(item.analysis_date)}</span>
              </>
            )}
          </div>
          {item.operation_advice && (
            <div className="mt-1.5">
              <span className="inline-block text-[10px] px-1.5 py-0.5 rounded-md bg-white/5 text-secondary">
                {item.operation_advice}
              </span>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onAnalyze(); }}
            className="rounded-lg p-1.5 text-muted hover:bg-cyan/10 hover:text-cyan transition"
            title="重新分析"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            className="rounded-lg p-1.5 text-muted hover:bg-danger/10 hover:text-danger transition"
            title="移除"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

/* ─── Analysis Drawer ─── */
const AnalysisDrawer: React.FC<{
  item: EnrichedWatchlistItem | null;
  onClose: () => void;
  onAnalyze: (code: string) => void;
  onViewFull: (code: string) => void;
}> = ({ item, onClose, onAnalyze, onViewFull }) => {
  if (!item) return null;

  const score = item.composite_score ?? item.sentiment_score;

  // Close on ESC
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl bg-base/95 backdrop-blur-xl border-l border-white/10 shadow-2xl overflow-y-auto animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-base/90 backdrop-blur-sm border-b border-white/8 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {score !== null && (
                <span className={`inline-flex items-center justify-center w-12 h-12 rounded-xl text-lg font-bold ${scoreBg(score)} ${scoreColor(score)}`}>
                  {Math.round(score)}
                </span>
              )}
              <div>
                <h2 className="text-lg font-semibold text-white">{item.name || item.code}</h2>
                <div className="flex items-center gap-2 text-xs text-muted">
                  <span className="font-mono">{item.code}</span>
                  {item.analysis_date && (
                    <>
                      <span className="text-white/20">·</span>
                      <span>{formatDate(item.analysis_date)}</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-muted hover:bg-white/10 hover:text-white transition"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-6">
          {/* Composite label / advice */}
          {(item.composite_label || item.operation_advice) && (
            <div className="flex items-center gap-2 flex-wrap">
              {item.composite_label && (
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${scoreBg(score)} ${scoreColor(score)}`}>
                  {item.composite_label}
                </span>
              )}
              {item.operation_advice && (
                <span className="px-3 py-1 rounded-full text-sm bg-white/5 text-secondary">
                  {item.operation_advice}
                </span>
              )}
              {item.trend_prediction && (
                <span className="px-3 py-1 rounded-full text-sm bg-white/5 text-secondary">
                  {item.trend_prediction}
                </span>
              )}
            </div>
          )}

          {/* Score breakdown */}
          {score !== null && (
            <div className="rounded-xl border border-white/8 bg-card/40 p-4 space-y-3">
              <h3 className="text-sm font-medium text-white mb-3">评分详情</h3>
              <ScoreBar label="技术面" score={item.technical_score} max={40} />
              <ScoreBar label="基本面" score={item.fundamental_score} max={30} />
              <ScoreBar label="资金流" score={item.money_flow_score} max={20} />
              <ScoreBar label="大盘" score={item.market_score} max={10} />
              {item.confidence_score !== null && (
                <div className="pt-2 mt-2 border-t border-white/5">
                  <ScoreBar label="置信度" score={item.confidence_score} max={100} />
                </div>
              )}
            </div>
          )}

          {/* Analysis summary */}
          {item.analysis_summary ? (
            <div className="rounded-xl border border-white/8 bg-card/40 p-4">
              <h3 className="text-sm font-medium text-white mb-3">分析摘要</h3>
              <p className="text-sm text-secondary leading-relaxed whitespace-pre-line">
                {item.analysis_summary}
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-white/10 bg-card/20 p-8 text-center">
              <p className="text-sm text-muted">暂无分析数据</p>
              <p className="text-xs text-muted mt-1">点击下方按钮开始分析</p>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => onAnalyze(item.code)}
              className="flex-1 btn-primary flex items-center justify-center gap-2 py-2.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              重新分析
            </button>
            <button
              type="button"
              onClick={() => onViewFull(item.code)}
              className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-secondary hover:bg-white/10 hover:text-white transition flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              详细报告
            </button>
          </div>
        </div>
      </div>
    </>
  );
};

/* ─── Main Page ─── */
const WatchlistPage: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<EnrichedWatchlistItem[]>([]);
  const [limit, setLimit] = useState(3);
  const [used, setUsed] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);
  const [stockCode, setStockCode] = useState('');
  const [inputError, setInputError] = useState<string>();
  const [isAdding, setIsAdding] = useState(false);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [analyzeConfirm, setAnalyzeConfirm] = useState<string | null>(null);

  const selectedItem = items.find((i) => i.code === selectedCode) ?? null;

  const fetchList = useCallback(async () => {
    try {
      setIsLoading(true);
      const [enrichedRes, quotaRes] = await Promise.all([
        watchlistApi.getEnrichedList(),
        watchlistApi.getQuota(),
      ]);
      setItems(enrichedRes.items);
      setLimit(quotaRes.limit);
      setUsed(quotaRes.used);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { void fetchList(); }, [fetchList]);

  const handleAdd = async () => {
    const { valid, message, normalized } = validateStockCode(stockCode);
    if (!valid) { setInputError(message); return; }
    setInputError(undefined);
    setIsAdding(true);
    try {
      await watchlistApi.add(normalized);
      setStockCode('');
      await fetchList();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsAdding(false);
    }
  };

  const handleRemove = async (code: string) => {
    try {
      await watchlistApi.remove(code);
      if (selectedCode === code) setSelectedCode(null);
      await fetchList();
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  const handleAnalyze = (code: string) => {
    setAnalyzeConfirm(code);
  };

  const confirmAnalyze = () => {
    if (!analyzeConfirm) return;
    // Navigate to chat page with pre-filled stock code
    navigate(`/chat?stock=${analyzeConfirm}`);
    setAnalyzeConfirm(null);
  };

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4 rounded-2xl border border-white/8 bg-card/80 p-4 backdrop-blur-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">自选股</h1>
            <p className="text-sm text-secondary">
              管理您关注的股票，点击卡片查看最近分析详情
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="rounded-lg bg-elevated px-3 py-1.5 text-secondary">
              {used} / {limit} 只
            </span>
          </div>
        </div>
      </header>

      {error && <ApiErrorAlert error={error} className="mb-4" />}

      {/* Add stock input */}
      <div className="mb-4 flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={stockCode}
            onChange={(e) => { setStockCode(e.target.value.toUpperCase()); setInputError(undefined); }}
            onKeyDown={(e) => { if (e.key === 'Enter' && stockCode && !isAdding) handleAdd(); }}
            placeholder="输入股票代码添加自选，如 600519"
            disabled={isAdding || used >= limit}
            className={`input-terminal w-full ${inputError ? 'border-danger/50' : ''}`}
          />
          {inputError && <p className="absolute -bottom-4 left-0 text-xs text-danger">{inputError}</p>}
        </div>
        <button
          type="button"
          onClick={handleAdd}
          disabled={!stockCode || isAdding || used >= limit}
          className="btn-primary whitespace-nowrap"
        >
          {isAdding ? '添加中...' : '添加'}
        </button>
      </div>
      {used >= limit && (
        <div className="mb-4 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-sm text-amber-400">
          已达自选股上限（{limit} 只），
          <button type="button" onClick={() => navigate('/pricing')} className="underline hover:text-amber-300">升级订阅</button>
          以添加更多。
        </div>
      )}

      {/* Watchlist grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-elevated">
            <svg className="h-6 w-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
            </svg>
          </div>
          <h3 className="text-base font-medium text-white mb-1">还没有自选股</h3>
          <p className="text-xs text-muted">添加股票代码开始跟踪分析</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <StockCard
              key={item.code}
              item={item}
              isActive={selectedCode === item.code}
              onClick={() => setSelectedCode(selectedCode === item.code ? null : item.code)}
              onRemove={() => handleRemove(item.code)}
              onAnalyze={() => handleAnalyze(item.code)}
            />
          ))}
        </div>
      )}

      {/* Analysis detail drawer */}
      {selectedItem && (
        <AnalysisDrawer
          item={selectedItem}
          onClose={() => setSelectedCode(null)}
          onAnalyze={handleAnalyze}
          onViewFull={(code) => navigate(`/?stock=${code}`)}
        />
      )}

      {/* Analyze confirmation dialog */}
      {analyzeConfirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-base/95 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2">确认分析</h3>
            <p className="text-sm text-secondary mb-4">
              重新分析 <span className="text-white font-medium">{analyzeConfirm}</span> 将消耗 1 次 Agent 调用次数。
              确认继续？
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setAnalyzeConfirm(null)}
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-secondary hover:bg-white/10 transition"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmAnalyze}
                className="flex-1 btn-primary py-2"
              >
                确认分析
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WatchlistPage;

import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { watchlistApi, type EnrichedWatchlistItem } from '../api/watchlist';
import { historyApi } from '../api/history';
import { analysisApi, DuplicateTaskError } from '../api/analysis';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert } from '../components/common';
import { ReportSummary } from '../components/report';
import { validateStockCode } from '../utils/validation';
import type { AnalysisReport } from '../types/analysis';

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
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${y}/${m}/${day} ${h}:${min}`;
}

/* ─── Stock Card (only remove button, no analyze) ─── */
const StockCard: React.FC<{
  item: EnrichedWatchlistItem;
  isActive: boolean;
  onClick: () => void;
  onRemove: () => void;
}> = ({ item, isActive, onClick, onRemove }) => {
  const score = item.composite_score ?? item.sentiment_score;
  const displayName = item.name && item.name !== item.code ? item.name : null;
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
            <h3 className="text-base font-bold text-white truncate">
              {displayName || item.code}
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

        {/* Remove button only */}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="shrink-0 rounded-lg p-1.5 text-muted opacity-0 group-hover:opacity-100 hover:bg-danger/10 hover:text-danger transition"
          title="移除"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
};

/* ─── Analysis Drawer with "开始分析" button ─── */
const AnalysisDrawer: React.FC<{
  analysisId: number | null;
  stockName: string;
  stockCode: string;
  isAnalyzing: boolean;
  analyzeStatus: string | null;
  onClose: () => void;
  onAnalyze: () => void;
}> = ({ analysisId, stockName, stockCode, isAnalyzing, analyzeStatus, onClose, onAnalyze }) => {
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load full report when analysisId changes
  useEffect(() => {
    if (!analysisId) return;
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);
    historyApi
      .getDetail(analysisId)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(getParsedApiError(err)?.message || 'Failed to load report');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [analysisId]);

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
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-3xl bg-base/95 backdrop-blur-xl border-l border-white/10 shadow-2xl overflow-y-auto animate-slide-in-right">
        {/* Header */}
        <div className="sticky top-0 z-10 bg-base/90 backdrop-blur-sm border-b border-white/8 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">{stockName || stockCode}</h2>
              <p className="text-xs text-muted font-mono">{stockCode}</p>
            </div>
            <div className="flex items-center gap-3">
              {/* Green "开始分析" button */}
              <button
                type="button"
                onClick={onAnalyze}
                disabled={isAnalyzing}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl font-medium text-sm text-white
                  bg-emerald-500 hover:bg-emerald-400 active:bg-emerald-600
                  disabled:opacity-50 disabled:cursor-not-allowed
                  shadow-lg shadow-emerald-500/20 transition-all duration-200"
              >
                {isAnalyzing ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    分析中...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                    开始分析
                  </>
                )}
              </button>
              {/* Close button */}
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
          {/* Analysis status feedback */}
          {analyzeStatus && (
            <div className={`mt-2 text-xs px-3 py-1.5 rounded-lg ${
              analyzeStatus.includes('失败') || analyzeStatus.includes('错误')
                ? 'bg-danger/10 text-danger'
                : 'bg-emerald-500/10 text-emerald-400'
            }`}>
              {analyzeStatus}
            </div>
          )}
        </div>

        {/* Content — reuse HomePage's ReportSummary */}
        <div className="px-4 py-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-10 h-10 border-3 border-cyan/20 border-t-cyan rounded-full animate-spin" />
              <p className="mt-3 text-secondary text-sm">加载报告中...</p>
            </div>
          ) : loadError ? (
            <div className="rounded-xl border border-danger/20 bg-danger/5 p-4 text-sm text-danger">
              {loadError}
            </div>
          ) : report ? (
            <ReportSummary data={report} isHistory />
          ) : !analysisId ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-12 h-12 mb-3 rounded-xl bg-elevated flex items-center justify-center">
                <svg className="w-6 h-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h3 className="text-base font-medium text-white mb-1">暂无分析数据</h3>
              <p className="text-xs text-muted mb-4">点击上方「开始分析」开始首次分析</p>
            </div>
          ) : null}
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

  // Analysis state (in-place, no navigation)
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeStatus, setAnalyzeStatus] = useState<string | null>(null);
  const [analyzeConfirm, setAnalyzeConfirm] = useState(false);

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

  // Open confirmation dialog from drawer "开始分析" button
  const handleAnalyzeClick = () => {
    setAnalyzeConfirm(true);
  };

  // Confirm and run analysis in-place (no navigation)
  const confirmAnalyze = async () => {
    if (!selectedCode) return;
    setAnalyzeConfirm(false);
    setIsAnalyzing(true);
    setAnalyzeStatus(null);
    try {
      const response = await analysisApi.analyzeAsync({
        stockCode: selectedCode,
        reportType: 'detailed',
      });
      setAnalyzeStatus(`分析任务已提交，请稍后刷新查看最新报告（任务ID: ${response.taskId.slice(0, 8)}...）`);
    } catch (err) {
      if (err instanceof DuplicateTaskError) {
        setAnalyzeStatus(`股票 ${err.stockCode} 正在分析中，请等待完成`);
      } else {
        setAnalyzeStatus(`分析失败：${getParsedApiError(err)?.message || '未知错误'}`);
      }
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Reset analyze status when drawer closes
  const handleDrawerClose = () => {
    setSelectedCode(null);
    setAnalyzeStatus(null);
    setAnalyzeConfirm(false);
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
            />
          ))}
        </div>
      )}

      {/* Analysis detail drawer */}
      {selectedItem && (
        <AnalysisDrawer
          analysisId={selectedItem.analysis_id}
          stockName={selectedItem.name || selectedItem.code}
          stockCode={selectedItem.code}
          isAnalyzing={isAnalyzing}
          analyzeStatus={analyzeStatus}
          onClose={handleDrawerClose}
          onAnalyze={handleAnalyzeClick}
        />
      )}

      {/* Analyze confirmation dialog */}
      {analyzeConfirm && selectedCode && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-base/95 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2">确认分析</h3>
            <p className="text-sm text-secondary mb-4">
              分析 <span className="text-white font-medium">{selectedItem?.name || selectedCode}</span> 将消耗 1 次 Agent 调用次数。
              确认继续？
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setAnalyzeConfirm(false)}
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-secondary hover:bg-white/10 transition"
              >
                取消
              </button>
              <button
                type="button"
                onClick={confirmAnalyze}
                className="flex-1 rounded-xl px-4 py-2 text-sm font-medium text-white bg-emerald-500 hover:bg-emerald-400 transition"
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

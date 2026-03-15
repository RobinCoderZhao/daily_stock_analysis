import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { watchlistApi, type WatchlistItem } from '../api/watchlist';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert } from '../components/common';
import { validateStockCode } from '../utils/validation';
import { useAuth } from '../hooks';

const WatchlistPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [limit, setLimit] = useState(3);
  const [used, setUsed] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);
  const [stockCode, setStockCode] = useState('');
  const [inputError, setInputError] = useState<string>();
  const [isAdding, setIsAdding] = useState(false);

  const fetchList = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await watchlistApi.getList();
      setItems(res.watchlist);
      setLimit(res.limit);
      setUsed(res.used);
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
      await fetchList();
    } catch (err) {
      setError(getParsedApiError(err));
    }
  };

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4 rounded-2xl border border-white/8 bg-card/80 p-4 backdrop-blur-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">自选股</h1>
            <p className="text-sm text-secondary">
              管理您关注的股票，系统将每日自动分析
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
                    d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
            </svg>
          </div>
          <h3 className="text-base font-medium text-white mb-1">还没有自选股</h3>
          <p className="text-xs text-muted">添加股票代码开始跟踪分析</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div
              key={item.stock_code}
              className="group rounded-2xl border border-white/8 bg-card/60 p-4 backdrop-blur-sm transition hover:border-white/16"
            >
              <div className="flex items-start justify-between">
                <button
                  type="button"
                  onClick={() => navigate(`/?stock=${item.stock_code}`)}
                  className="text-left"
                >
                  <h3 className="text-sm font-semibold text-white">{item.stock_code}</h3>
                  <p className="text-xs text-secondary">{item.stock_name || '—'}</p>
                </button>
                <button
                  type="button"
                  onClick={() => handleRemove(item.stock_code)}
                  className="rounded-lg p-1.5 text-muted opacity-0 transition hover:bg-danger/10 hover:text-danger group-hover:opacity-100"
                  title="移除"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>
              {item.composite_score !== undefined && (
                <div className="mt-3 flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-cyan to-emerald-400"
                      style={{ width: `${Math.min(100, Math.max(0, item.composite_score))}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium text-cyan">{item.composite_score}</span>
                </div>
              )}
              {item.latest_analysis_at && (
                <p className="mt-2 text-xs text-muted">最近分析: {item.latest_analysis_at}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WatchlistPage;

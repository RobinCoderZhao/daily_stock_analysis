import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  SignalItem,
  SignalsResponse,
  SignalSummary,
  SignalCreateRequest,
  StrategyPerformanceItem,
  StrategyRankingResponse,
  StrategyBacktestRunRequest,
  StrategyBacktestRunResponse,
} from '../types/signals';

// ============ Signals API ============

export const signalsApi = {
  /**
   * Get paginated signals list
   */
  getSignals: async (params: {
    status?: string;
    code?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<SignalsResponse> => {
    const { status, code, page = 1, limit = 20 } = params;
    const queryParams: Record<string, string | number> = { page, limit };
    if (status) queryParams.status = status;
    if (code) queryParams.code = code;

    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/signals/',
      { params: queryParams },
    );
    const data = toCamelCase<SignalsResponse>(response.data);
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: (data.items || []).map(item => toCamelCase<SignalItem>(item)),
    };
  },

  /**
   * Get signal performance summary
   */
  getSummary: async (): Promise<SignalSummary> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/signals/summary',
    );
    return toCamelCase<SignalSummary>(response.data);
  },

  /**
   * Get signal detail
   */
  getSignalById: async (id: number): Promise<SignalItem> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/signals/${id}`,
    );
    return toCamelCase<SignalItem>(response.data);
  },

  /**
   * Create a signal manually
   */
  createSignal: async (data: SignalCreateRequest): Promise<{ signalId: number; message: string }> => {
    const requestData: Record<string, unknown> = {
      code: data.code,
      entry_price: data.entryPrice,
    };
    if (data.stockName) requestData.stock_name = data.stockName;
    if (data.strategyName) requestData.strategy_name = data.strategyName;
    if (data.direction) requestData.direction = data.direction;
    if (data.stopLoss != null) requestData.stop_loss = data.stopLoss;
    if (data.takeProfit != null) requestData.take_profit = data.takeProfit;
    if (data.positionPct != null) requestData.position_pct = data.positionPct;
    if (data.confidence != null) requestData.confidence = data.confidence;
    if (data.holdingDays != null) requestData.holding_days = data.holdingDays;

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/signals/',
      requestData,
    );
    return toCamelCase<{ signalId: number; message: string }>(response.data);
  },

  /**
   * Close a signal
   */
  closeSignal: async (id: number): Promise<{ message: string }> => {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/signals/${id}/close`,
    );
    return toCamelCase<{ message: string }>(response.data);
  },

  /**
   * Get strategy performance ranking
   */
  getStrategyRanking: async (): Promise<StrategyRankingResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/signals/strategy-ranking',
    );
    const data = toCamelCase<StrategyRankingResponse>(response.data);
    return {
      strategies: (data.strategies || []).map(s => toCamelCase<StrategyPerformanceItem>(s)),
    };
  },

  /**
   * Run strategy-level backtest
   */
  runStrategyBacktest: async (params: StrategyBacktestRunRequest = {}): Promise<StrategyBacktestRunResponse> => {
    const requestData: Record<string, unknown> = {};
    if (params.strategyName) requestData.strategy_name = params.strategyName;
    if (params.code) requestData.code = params.code;
    if (params.limitStocks != null) requestData.limit_stocks = params.limitStocks;
    if (params.evalWindowDays != null) requestData.eval_window_days = params.evalWindowDays;

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/signals/strategy-backtest',
      requestData,
    );
    const data = toCamelCase<StrategyBacktestRunResponse>(response.data);
    return {
      strategiesTested: data.strategiesTested,
      results: (data.results || []).map(r => toCamelCase<StrategyPerformanceItem>(r)),
      error: data.error,
    };
  },
};

/**
 * Signal & Strategy Backtest type definitions
 * Mirrors api/v1/schemas/signals.py
 */

// ============ Signal Types ============

export interface SignalItem {
  id: number;
  analysisHistoryId?: number;
  code: string;
  stockName?: string;
  strategyName?: string;
  direction: string;
  entryPrice?: number;
  stopLoss?: number;
  takeProfit?: number;
  positionPct?: number;
  confidence?: number;
  status: string;
  createdAt?: string;
  closedAt?: string;
  currentPrice?: number;
  returnPct?: number;
  holdingDays?: number;
  expireDate?: string;
}

export interface SignalsResponse {
  total: number;
  page: number;
  limit: number;
  items: SignalItem[];
}

export interface SignalSummary {
  totalSignals: number;
  activeCount: number;
  closedCount: number;
  winCount: number;
  lossCount: number;
  winRatePct?: number;
  avgReturnPct?: number;
}

export interface SignalCreateRequest {
  code: string;
  stockName?: string;
  strategyName?: string;
  direction?: string;
  entryPrice: number;
  stopLoss?: number;
  takeProfit?: number;
  positionPct?: number;
  confidence?: number;
  holdingDays?: number;
}

// ============ Strategy Performance Types ============

export interface StrategyPerformanceItem {
  strategyName: string;
  totalSignals: number;
  winCount: number;
  lossCount: number;
  neutralCount: number;
  winRatePct?: number;
  avgReturnPct?: number;
  maxDrawdownPct?: number;
  profitFactor?: number;
  sharpeRatio?: number;
  avgHoldingDays?: number;
  stopLossTriggerRate?: number;
  takeProfitTriggerRate?: number;
  computedConfidence?: number;
  computedAt?: string;
}

export interface StrategyRankingResponse {
  strategies: StrategyPerformanceItem[];
}

export interface StrategyBacktestRunRequest {
  strategyName?: string;
  code?: string;
  limitStocks?: number;
  evalWindowDays?: number;
}

export interface StrategyBacktestRunResponse {
  strategiesTested: number;
  results: StrategyPerformanceItem[];
  error?: string;
}

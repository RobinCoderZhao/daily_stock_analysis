import type React from 'react';
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks';
import { paymentApi, type PlansResponse } from '../api/payment';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert } from '../components/common';

const TIER_ORDER = ['free', 'standard', 'pro'] as const;
const TIER_META: Record<string, { label: string; desc: string; accent: string; badge: string }> = {
  free: { label: '免费版', desc: '7 天试用体验', accent: 'border-white/10', badge: 'bg-white/5 text-secondary' },
  standard: { label: '标准版', desc: '进阶分析能力', accent: 'border-cyan/30', badge: 'bg-cyan/10 text-cyan' },
  pro: { label: '专业版', desc: '无限制全功能', accent: 'border-purple/30', badge: 'bg-purple/10 text-purple' },
};

const FEATURE_LABELS: Record<string, string> = {
  basic_analysis: '基础股票分析',
  agent_chat: 'AI Agent 对话',
  backtest: '策略回测',
  signals: '交易信号',
  export: '数据导出',
  api_access: 'API 访问',
};

const PricingPage: React.FC = () => {
  const { user, saasMode, loggedIn } = useAuth();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try { setPlans(await paymentApi.getPlans()); } catch (e) { setError(getParsedApiError(e)); }
      finally { setIsLoading(false); }
    })();
  }, []);

  const handleCheckout = async (plan: string) => {
    if (!loggedIn) { navigate('/login?redirect=/pricing'); return; }
    setCheckoutLoading(plan);
    try {
      const res = await paymentApi.createCheckout(plan);
      if (res.checkout_url) { window.location.href = res.checkout_url; }
      else { setError(getParsedApiError(res.error || 'Payment provider not configured')); }
    } catch (e) { setError(getParsedApiError(e)); }
    finally { setCheckoutLoading(null); }
  };

  const currentTier = user?.tier || 'free';

  if (isLoading) return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
    </div>
  );

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-white">选择会员方案</h1>
        <p className="mt-1 text-sm text-secondary">解锁更强大的分析能力</p>
      </header>

      {error && <ApiErrorAlert error={error} className="mx-auto mb-4 max-w-2xl" />}

      {/* Tier cards */}
      <div className="mx-auto grid max-w-4xl gap-4 md:grid-cols-3">
        {plans && TIER_ORDER.map((tier) => {
          const cfg = plans.tiers[tier];
          const meta = TIER_META[tier];
          if (!cfg) return null;
          const isCurrent = tier === currentTier;
          return (
            <div key={tier} className={`relative rounded-2xl border ${meta.accent} bg-card/60 p-5 backdrop-blur-sm transition ${
              tier === 'standard' ? 'ring-1 ring-cyan/20' : ''
            }`}>
              {tier === 'standard' && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-cyan px-3 py-0.5 text-xs font-semibold text-black">
                  推荐
                </span>
              )}
              <div className="mb-4">
                <span className={`inline-block rounded-lg px-2.5 py-1 text-xs font-semibold ${meta.badge}`}>{meta.label}</span>
                <p className="mt-1 text-xs text-muted">{meta.desc}</p>
              </div>
              <div className="mb-4">
                <span className="text-3xl font-bold text-white">
                  ¥{(cfg.price_monthly_cents / 100).toFixed(0)}
                </span>
                <span className="text-sm text-muted">/月</span>
              </div>
              <ul className="mb-5 space-y-2">
                <li className="flex items-center gap-2 text-sm text-secondary">
                  <CheckIcon /> 自选股 {cfg.watchlist_limit} 只
                </li>
                <li className="flex items-center gap-2 text-sm text-secondary">
                  <CheckIcon /> Agent {cfg.agent_daily_limit === null ? '无限' : `${cfg.agent_daily_limit} 次/日`}
                </li>
                {cfg.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-secondary">
                    <CheckIcon /> {FEATURE_LABELS[f] || f}
                  </li>
                ))}
              </ul>
              {isCurrent ? (
                <button disabled className="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 text-sm text-muted">当前方案</button>
              ) : tier === 'free' ? (
                <button disabled className="w-full rounded-xl border border-white/10 bg-white/5 py-2.5 text-sm text-muted">默认方案</button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleCheckout(`${tier}_monthly`)}
                  disabled={checkoutLoading !== null}
                  className={`w-full rounded-xl py-2.5 text-sm font-semibold transition ${
                    tier === 'pro' ? 'bg-purple text-white hover:bg-purple/90' : 'btn-primary'
                  }`}
                >
                  {checkoutLoading === `${tier}_monthly` ? '处理中...' : '选择方案'}
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Temp packs */}
      {plans?.temp_packs && Object.keys(plans.temp_packs).length > 0 && (
        <div className="mx-auto mt-8 max-w-4xl">
          <h2 className="mb-3 text-lg font-semibold text-white">补充次数包</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.entries(plans.temp_packs).map(([key, pack]) => (
              <div key={key} className="rounded-2xl border border-white/8 bg-card/60 p-4 backdrop-blur-sm">
                <p className="text-lg font-bold text-white">{pack.credits} 次</p>
                <p className="text-sm text-secondary">¥{(pack.price_cents / 100).toFixed(0)}</p>
                <p className="mb-3 text-xs text-muted">¥{(pack.price_cents / pack.credits / 100).toFixed(1)}/次</p>
                <button
                  type="button"
                  onClick={() => handleCheckout(key)}
                  disabled={checkoutLoading !== null}
                  className="btn-secondary w-full text-sm"
                >
                  {checkoutLoading === key ? '处理中...' : '购买'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const CheckIcon: React.FC = () => (
  <svg className="h-4 w-4 flex-shrink-0 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/>
  </svg>
);

export default PricingPage;

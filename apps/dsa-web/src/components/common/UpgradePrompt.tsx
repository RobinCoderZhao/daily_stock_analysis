import type React from 'react';
import { useNavigate } from 'react-router-dom';

type UpgradePromptProps = {
  title?: string;
  message?: string;
  feature?: string;
  tier?: string;
  className?: string;
};

/**
 * Upgrade prompt shown when user hits quota/feature limits.
 * Handles 403 feature_not_available and 429 agent_daily_limit_reached.
 */
const UpgradePrompt: React.FC<UpgradePromptProps> = ({
  title = '功能受限',
  message = '此功能需要升级至更高会员等级',
  feature,
  tier,
  className = '',
}) => {
  const navigate = useNavigate();

  return (
    <div className={`rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 text-center ${className}`}>
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10">
        <svg className="h-6 w-6 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
        </svg>
      </div>
      <h3 className="mb-1.5 text-base font-semibold text-white">{title}</h3>
      <p className="mb-4 text-sm text-secondary">{message}</p>
      {feature && (
        <p className="mb-2 text-xs text-muted">
          需要功能：<span className="text-amber-400">{feature}</span>
          {tier && <> · 当前等级：<span className="text-cyan">{tier}</span></>}
        </p>
      )}
      <button
        type="button"
        onClick={() => navigate('/pricing')}
        className="btn-primary"
      >
        查看会员方案
      </button>
    </div>
  );
};

export default UpgradePrompt;

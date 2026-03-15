import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks';
import { paymentApi, type SubscriptionInfo, type OrderItem } from '../api/payment';
import { profileApi, type MemoryItem, type InvestmentProfileData } from '../api/profile';
import { getParsedApiError } from '../api/error';
import { ApiErrorAlert } from '../components/common';

const TIER_LABELS: Record<string, string> = { free: '免费版', standard: '标准版', pro: '专业版', none: '未订阅' };
const STATUS_LABELS: Record<string, string> = { active: '有效', expired: '已过期', cancelled: '已取消', inactive: '未激活' };

const ProfilePage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState<'subscription' | 'profile' | 'memories' | 'orders'>('subscription');
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);

  // Subscription
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [subLoading, setSubLoading] = useState(true);

  // Investment profile
  const [investProfile, setInvestProfile] = useState<InvestmentProfileData | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Memories
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memLoading, setMemLoading] = useState(false);

  // Orders
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);

  const loadSub = useCallback(async () => {
    setSubLoading(true);
    try { setSub(await paymentApi.getSubscription()); setError(null); }
    catch (e) { setError(getParsedApiError(e)); } finally { setSubLoading(false); }
  }, []);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    try { setInvestProfile(await profileApi.getInvestmentProfile()); setError(null); }
    catch (e) { setError(getParsedApiError(e)); } finally { setProfileLoading(false); }
  }, []);

  const loadMemories = useCallback(async () => {
    setMemLoading(true);
    try { const res = await profileApi.getMemories(); setMemories(res.memories || []); setError(null); }
    catch (e) { setError(getParsedApiError(e)); } finally { setMemLoading(false); }
  }, []);

  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    try { const res = await paymentApi.getOrders(); setOrders(res.orders || []); setError(null); }
    catch (e) { setError(getParsedApiError(e)); } finally { setOrdersLoading(false); }
  }, []);

  useEffect(() => { void loadSub(); }, [loadSub]);
  useEffect(() => { if (tab === 'profile') void loadProfile(); }, [tab, loadProfile]);
  useEffect(() => { if (tab === 'memories') void loadMemories(); }, [tab, loadMemories]);
  useEffect(() => { if (tab === 'orders') void loadOrders(); }, [tab, loadOrders]);

  const handleCancel = async () => {
    if (!confirm('确定取消订阅？当前订阅将持续到到期日。')) return;
    try { await paymentApi.cancelSubscription(); await loadSub(); } catch (e) { setError(getParsedApiError(e)); }
  };

  const handleDeleteMemory = async (id: string) => {
    try { await profileApi.deleteMemory(id); setMemories((p) => p.filter((m) => m.id !== id)); } catch (e) { setError(getParsedApiError(e)); }
  };

  const handleClearAll = async () => {
    if (!confirm('确定清空所有记忆？此操作不可撤销。')) return;
    try { await profileApi.clearAllMemories(); setMemories([]); } catch (e) { setError(getParsedApiError(e)); }
  };

  const tabs = [
    { key: 'subscription' as const, label: '订阅概览' },
    { key: 'profile' as const, label: '投资画像' },
    { key: 'memories' as const, label: '记忆管理' },
    { key: 'orders' as const, label: '订单历史' },
  ];

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4 rounded-2xl border border-white/8 bg-card/80 p-4 backdrop-blur-sm">
        <h1 className="text-xl font-semibold text-white">个人中心</h1>
        <p className="text-sm text-secondary">{user?.email}</p>
      </header>

      {error && <ApiErrorAlert error={error} className="mb-4" />}

      {/* Tabs */}
      <div className="mb-4 flex gap-1 rounded-xl border border-white/8 bg-card/40 p-1">
        {tabs.map((t) => (
          <button
            key={t.key} type="button"
            onClick={() => setTab(t.key)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === t.key ? 'bg-cyan/10 text-cyan border border-cyan/20' : 'text-secondary hover:text-white'
            }`}
          >{t.label}</button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="rounded-2xl border border-white/8 bg-card/60 p-5 backdrop-blur-sm">
        {tab === 'subscription' && (
          subLoading ? <Spinner /> : sub ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <span className={`rounded-lg px-3 py-1 text-sm font-semibold ${
                  sub.tier === 'pro' ? 'bg-purple/10 text-purple border border-purple/20' :
                  sub.tier === 'standard' ? 'bg-cyan/10 text-cyan border border-cyan/20' :
                  'bg-white/5 text-secondary border border-white/10'
                }`}>{TIER_LABELS[sub.tier] || sub.tier}</span>
                <span className="text-sm text-secondary">{STATUS_LABELS[sub.status] || sub.status}</span>
              </div>
              {sub.expire_at && <p className="text-sm text-secondary">到期时间：{sub.expire_at}</p>}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatCard label="自选股上限" value={sub.watchlist_limit ?? '—'} />
                <StatCard label="Agent 每日限额" value={sub.agent_daily_limit === null ? '无限' : String(sub.agent_daily_limit ?? 0)} />
                <StatCard label="临时分析次数" value={sub.temp_analysis_credits ?? 0} />
              </div>
              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => navigate('/pricing')} className="btn-primary">升级 / 续费</button>
                {sub.status === 'active' && sub.tier !== 'free' && (
                  <button type="button" onClick={handleCancel} className="btn-secondary">取消订阅</button>
                )}
              </div>
            </div>
          ) : <p className="text-secondary">无法加载订阅信息</p>
        )}

        {tab === 'profile' && (
          profileLoading ? <Spinner /> : investProfile ? (
            <div className="space-y-3">
              <h3 className="text-base font-semibold text-white">AI 提取的投资画像</h3>
              <p className="text-xs text-muted">基于 {investProfile.memory_count} 条对话记忆提取</p>
              <pre className="rounded-xl bg-elevated/60 p-4 text-sm text-secondary overflow-auto whitespace-pre-wrap">
                {JSON.stringify(investProfile.profile, null, 2)}
              </pre>
            </div>
          ) : <p className="text-sm text-secondary">暂无投资画像数据，与 AI Agent 对话后自动生成。</p>
        )}

        {tab === 'memories' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold text-white">记忆列表</h3>
              {memories.length > 0 && (
                <button type="button" onClick={handleClearAll} className="text-xs text-danger hover:text-danger/80">
                  清空全部
                </button>
              )}
            </div>
            {memLoading ? <Spinner /> : memories.length === 0 ? (
              <p className="text-sm text-secondary">暂无记忆，与 AI Agent 对话后自动积累。</p>
            ) : (
              <div className="space-y-2">
                {memories.map((m) => (
                  <div key={m.id} className="group flex items-start gap-3 rounded-xl border border-white/8 bg-elevated/40 p-3">
                    <p className="flex-1 text-sm text-secondary">{m.memory}</p>
                    <button
                      type="button" onClick={() => handleDeleteMemory(m.id)}
                      className="rounded p-1 text-muted opacity-0 transition hover:text-danger group-hover:opacity-100"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'orders' && (
          ordersLoading ? <Spinner /> : orders.length === 0 ? (
            <p className="text-sm text-secondary">暂无订单记录</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/8 text-left text-xs text-muted">
                    <th className="pb-2">订单号</th><th className="pb-2">方案</th><th className="pb-2">金额</th>
                    <th className="pb-2">状态</th><th className="pb-2">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.order_no} className="border-b border-white/5 text-secondary">
                      <td className="py-2 font-mono text-xs">{o.order_no.slice(-12)}</td>
                      <td className="py-2">{o.plan}</td>
                      <td className="py-2">¥{(o.amount_cents / 100).toFixed(2)}</td>
                      <td className="py-2"><span className={o.status === 'paid' ? 'text-emerald-400' : ''}>{o.status}</span></td>
                      <td className="py-2 text-xs">{o.created_at?.split('T')[0]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
};

const Spinner: React.FC = () => (
  <div className="flex justify-center py-8">
    <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
  </div>
);

const StatCard: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-xl border border-white/8 bg-elevated/40 p-3">
    <p className="text-xs text-muted">{label}</p>
    <p className="mt-1 text-lg font-semibold text-white">{value}</p>
  </div>
);

export default ProfilePage;

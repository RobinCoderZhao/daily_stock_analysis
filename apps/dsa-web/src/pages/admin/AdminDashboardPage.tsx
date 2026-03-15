import type React from 'react';
import { useState, useEffect } from 'react';
import { adminApi, type DashboardOverview, type GrowthDataPoint, type UsageDataPoint, type RevenueDataPoint, type LlmCostDataPoint } from '../../api/admin';
import { getParsedApiError } from '../../api/error';
import { ApiErrorAlert } from '../../components/common';

const AdminDashboardPage: React.FC = () => {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [growth, setGrowth] = useState<GrowthDataPoint[]>([]);
  const [usage, setUsage] = useState<UsageDataPoint[]>([]);
  const [revenue, setRevenue] = useState<RevenueDataPoint[]>([]);
  const [llmCost, setLlmCost] = useState<LlmCostDataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [ov, gr, us, rev, llm] = await Promise.all([
          adminApi.getOverview(),
          adminApi.getUserGrowth(),
          adminApi.getUsageStats(),
          adminApi.getRevenue(),
          adminApi.getLlmCost(),
        ]);
        setOverview(ov); setGrowth(gr.data); setUsage(us.data); setRevenue(rev.data); setLlmCost(llm.data);
      } catch (e) { setError(getParsedApiError(e)); }
      finally { setIsLoading(false); }
    })();
  }, []);

  if (isLoading) return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
    </div>
  );

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4">
        <h1 className="text-xl font-semibold text-white">管理看板</h1>
        <p className="text-sm text-secondary">平台运营数据总览</p>
      </header>

      {error && <ApiErrorAlert error={error} className="mb-4" />}

      {/* KPI Cards */}
      {overview && (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <KpiCard label="总用户" value={overview.total_users} />
          <KpiCard label="今日活跃" value={overview.active_today} accent="cyan" />
          <KpiCard label="活跃订阅" value={overview.active_subscriptions} accent="purple" />
          <KpiCard label="月收入" value={`¥${(overview.monthly_revenue_cents / 100).toFixed(0)}`} accent="emerald" />
          <KpiCard label="今日调用" value={overview.today_usage} accent="amber" />
        </div>
      )}

      {/* Charts — simple bar representations without external lib */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* User growth */}
        <ChartSection title="用户注册趋势（30天）">
          {growth.length > 0 ? (
            <SimpleBarChart data={growth.map((d) => ({ label: d.date.slice(5), value: d.registrations }))} />
          ) : <p className="text-sm text-muted">暂无数据</p>}
        </ChartSection>

        {/* Usage */}
        <ChartSection title="调用量统计（30天）">
          {usage.length > 0 ? (
            <SimpleBarChart data={usage.map((d) => ({ label: `${d.date.slice(5)} ${d.action}`, value: d.count }))} />
          ) : <p className="text-sm text-muted">暂无数据</p>}
        </ChartSection>

        {/* Revenue */}
        <ChartSection title="收入统计（30天）">
          {revenue.length > 0 ? (
            <SimpleBarChart data={revenue.map((d) => ({ label: `${d.date.slice(5)} ${d.plan}`, value: d.total_cents / 100 }))} unit="¥" />
          ) : <p className="text-sm text-muted">暂无数据</p>}
        </ChartSection>

        {/* LLM Cost */}
        <ChartSection title="LLM 调用统计">
          {llmCost.length > 0 ? (
            <div className="space-y-2">
              {llmCost.map((c) => (
                <div key={c.action} className="flex items-center justify-between rounded-lg bg-elevated/40 p-3">
                  <span className="text-sm text-secondary">{c.action}</span>
                  <div className="flex gap-4 text-sm">
                    <span className="text-muted">{c.call_count} 次</span>
                    <span className="text-white font-medium">{(c.total_tokens / 1000).toFixed(1)}K tokens</span>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-muted">暂无数据</p>}
        </ChartSection>
      </div>
    </div>
  );
};

// ── Sub components ──

const KpiCard: React.FC<{ label: string; value: string | number; accent?: string }> = ({ label, value, accent }) => (
  <div className="rounded-2xl border border-white/8 bg-card/60 p-4 backdrop-blur-sm">
    <p className="text-xs text-muted">{label}</p>
    <p className={`mt-1 text-2xl font-bold ${accent ? `text-${accent}` : 'text-white'}`}>{value}</p>
  </div>
);

const ChartSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="rounded-2xl border border-white/8 bg-card/60 p-4 backdrop-blur-sm">
    <h3 className="mb-3 text-sm font-semibold text-white">{title}</h3>
    {children}
  </div>
);

const SimpleBarChart: React.FC<{ data: { label: string; value: number }[]; unit?: string }> = ({ data, unit = '' }) => {
  const max = Math.max(...data.map((d) => d.value), 1);
  const recent = data.slice(-15); // Show last 15 items
  return (
    <div className="flex items-end gap-1" style={{ height: 120 }}>
      {recent.map((d, i) => (
        <div key={i} className="group relative flex flex-1 flex-col items-center justify-end">
          <div
            className="w-full min-w-[4px] rounded-t bg-gradient-to-t from-cyan/60 to-cyan transition-all group-hover:from-cyan/80 group-hover:to-cyan"
            style={{ height: `${Math.max(4, (d.value / max) * 100)}%` }}
          />
          <span className="mt-1 hidden text-[9px] text-muted group-hover:block absolute -top-5 whitespace-nowrap bg-elevated px-1 rounded">
            {unit}{d.value}
          </span>
        </div>
      ))}
    </div>
  );
};

export default AdminDashboardPage;

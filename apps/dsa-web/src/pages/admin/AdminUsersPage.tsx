import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { adminApi, type AdminUser, type AdminUserDetail } from '../../api/admin';
import { getParsedApiError } from '../../api/error';
import { ApiErrorAlert } from '../../components/common';

const TIER_LABELS: Record<string, string> = { free: '免费', standard: '标准', pro: '专业', none: '—' };

const AdminUsersPage: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);

  // Detail drawer
  const [detail, setDetail] = useState<AdminUserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Adjust modal
  const [adjustUserId, setAdjustUserId] = useState<number | null>(null);
  const [adjTier, setAdjTier] = useState('');
  const [adjCredits, setAdjCredits] = useState('');
  const [adjDays, setAdjDays] = useState('');

  const limit = 20;

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await adminApi.listUsers(page, limit, search || undefined);
      setUsers(res.users); setTotal(res.total); setError(null);
    } catch (e) { setError(getParsedApiError(e)); }
    finally { setIsLoading(false); }
  }, [page, search]);

  useEffect(() => { void fetchUsers(); }, [fetchUsers]);

  const handleSearch = () => { setPage(1); fetchUsers(); };

  const toggleStatus = async (u: AdminUser) => {
    const newStatus = u.status === 'active' ? 'suspended' : 'active';
    if (!confirm(`确定${newStatus === 'suspended' ? '冻结' : '解冻'}用户 ${u.email}？`)) return;
    try { await adminApi.updateUserStatus(u.id, newStatus); await fetchUsers(); } catch (e) { setError(getParsedApiError(e)); }
  };

  const showDetail = async (userId: number) => {
    setDetailLoading(true);
    try { const d = await adminApi.getUserDetail(userId); setDetail(d); } catch (e) { setError(getParsedApiError(e)); }
    finally { setDetailLoading(false); }
  };

  const handleAdjust = async () => {
    if (!adjustUserId) return;
    const body: { tier?: string; temp_credits?: number; extend_days?: number } = {};
    if (adjTier) body.tier = adjTier;
    if (adjCredits) body.temp_credits = parseInt(adjCredits, 10);
    if (adjDays) body.extend_days = parseInt(adjDays, 10);
    try {
      await adminApi.adjustSubscription(adjustUserId, body);
      setAdjustUserId(null); setAdjTier(''); setAdjCredits(''); setAdjDays('');
      await fetchUsers();
    } catch (e) { setError(getParsedApiError(e)); }
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">用户管理</h1>
          <p className="text-sm text-secondary">共 {total} 名用户</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text" value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            placeholder="搜索邮箱/昵称"
            className="input-terminal w-48"
          />
          <button type="button" onClick={handleSearch} className="btn-secondary text-sm">搜索</button>
        </div>
      </header>

      {error && <ApiErrorAlert error={error} className="mb-4" />}

      {/* Users table */}
      <div className="overflow-x-auto rounded-2xl border border-white/8 bg-card/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/8 text-left text-xs text-muted">
                <th className="p-3">ID</th><th className="p-3">邮箱</th><th className="p-3">昵称</th>
                <th className="p-3">角色</th><th className="p-3">状态</th><th className="p-3">注册时间</th>
                <th className="p-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-white/5 text-secondary hover:bg-white/2">
                  <td className="p-3">{u.id}</td>
                  <td className="p-3 text-white">{u.email}</td>
                  <td className="p-3">{u.nickname || '—'}</td>
                  <td className="p-3"><RoleBadge role={u.role} /></td>
                  <td className="p-3"><StatusBadge status={u.status} /></td>
                  <td className="p-3 text-xs">{u.created_at?.split('T')[0]}</td>
                  <td className="p-3">
                    <div className="flex gap-1">
                      <button type="button" onClick={() => showDetail(u.id)}
                        className="rounded px-2 py-1 text-xs text-cyan hover:bg-cyan/10">详情</button>
                      <button type="button" onClick={() => toggleStatus(u)}
                        className={`rounded px-2 py-1 text-xs ${u.status === 'active' ? 'text-amber-400 hover:bg-amber-400/10' : 'text-emerald-400 hover:bg-emerald-400/10'}`}>
                        {u.status === 'active' ? '冻结' : '解冻'}
                      </button>
                      <button type="button" onClick={() => setAdjustUserId(u.id)}
                        className="rounded px-2 py-1 text-xs text-purple hover:bg-purple/10">调整</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-3 flex items-center justify-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="btn-secondary text-xs">上一页</button>
          <span className="text-sm text-secondary">{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="btn-secondary text-xs">下一页</button>
        </div>
      )}

      {/* Detail drawer */}
      {detail && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative w-80 bg-base border-l border-white/10 p-5 overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={() => setDetail(null)} className="absolute top-3 right-3 text-muted hover:text-white">✕</button>
            <h3 className="text-base font-semibold text-white mb-3">用户详情</h3>
            {detailLoading ? <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan mx-auto" /> : (
              <div className="space-y-3 text-sm">
                <Row label="ID" value={detail.user.id} />
                <Row label="邮箱" value={detail.user.email} />
                <Row label="昵称" value={detail.user.nickname || '—'} />
                <Row label="角色" value={detail.user.role} />
                <Row label="今日用量" value={detail.usage_today} />
                {detail.subscription && (
                  <>
                    <hr className="border-white/8" />
                    <Row label="等级" value={TIER_LABELS[detail.subscription.tier] || detail.subscription.tier} />
                    <Row label="状态" value={detail.subscription.status} />
                    <Row label="到期" value={detail.subscription.expire_at || '—'} />
                    <Row label="临时次数" value={detail.subscription.temp_credits} />
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Adjust modal */}
      {adjustUserId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setAdjustUserId(null)}>
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative w-96 rounded-2xl bg-base border border-white/10 p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-white mb-4">调整订阅 — 用户 #{adjustUserId}</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted">等级</label>
                <select value={adjTier} onChange={(e) => setAdjTier(e.target.value)} className="input-terminal w-full mt-1">
                  <option value="">不变</option>
                  <option value="free">免费</option>
                  <option value="standard">标准</option>
                  <option value="pro">专业</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-muted">增加临时次数</label>
                <input type="number" value={adjCredits} onChange={(e) => setAdjCredits(e.target.value)} placeholder="0" className="input-terminal w-full mt-1" />
              </div>
              <div>
                <label className="text-xs text-muted">延长天数</label>
                <input type="number" value={adjDays} onChange={(e) => setAdjDays(e.target.value)} placeholder="0" className="input-terminal w-full mt-1" />
              </div>
            </div>
            <div className="mt-4 flex gap-2 justify-end">
              <button type="button" onClick={() => setAdjustUserId(null)} className="btn-secondary text-sm">取消</button>
              <button type="button" onClick={handleAdjust} className="btn-primary text-sm">确认调整</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Sub components
const RoleBadge: React.FC<{ role: string }> = ({ role }) => (
  <span className={`rounded px-1.5 py-0.5 text-xs ${
    role === 'super_admin' ? 'bg-purple/10 text-purple' :
    role === 'admin' ? 'bg-cyan/10 text-cyan' :
    'bg-white/5 text-muted'
  }`}>{role}</span>
);

const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span className={`rounded px-1.5 py-0.5 text-xs ${
    status === 'active' ? 'bg-emerald-400/10 text-emerald-400' : 'bg-danger/10 text-danger'
  }`}>{status === 'active' ? '正常' : '冻结'}</span>
);

const Row: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="flex items-center justify-between">
    <span className="text-muted">{label}</span>
    <span className="text-white">{value}</span>
  </div>
);

export default AdminUsersPage;

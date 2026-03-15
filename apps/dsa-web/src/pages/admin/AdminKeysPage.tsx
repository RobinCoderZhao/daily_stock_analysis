import type React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { adminApi, type PlatformKey, type KeyUsageStat } from '../../api/admin';
import { getParsedApiError } from '../../api/error';
import { ApiErrorAlert } from '../../components/common';

const PROVIDERS = ['gemini', 'openai', 'deepseek', 'anthropic', 'tavily', 'bocha'] as const;

const AdminKeysPage: React.FC = () => {
  const [keys, setKeys] = useState<PlatformKey[]>([]);
  const [usageStats, setUsageStats] = useState<KeyUsageStat[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ReturnType<typeof getParsedApiError> | null>(null);

  // Add key modal
  const [showAdd, setShowAdd] = useState(false);
  const [newProvider, setNewProvider] = useState('');
  const [newRawKey, setNewRawKey] = useState('');
  const [newPriority, setNewPriority] = useState('0');
  const [newDailyLimit, setNewDailyLimit] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [addLoading, setAddLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [k, u] = await Promise.all([adminApi.listKeys(), adminApi.getKeyUsage()]);
      setKeys(k.keys); setUsageStats(u.stats); setError(null);
    } catch (e) { setError(getParsedApiError(e)); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { void fetchData(); }, [fetchData]);

  const handleAdd = async () => {
    if (!newProvider || !newRawKey) return;
    setAddLoading(true);
    try {
      await adminApi.addKey({
        provider: newProvider, raw_key: newRawKey,
        priority: parseInt(newPriority, 10) || 0,
        daily_limit: newDailyLimit ? parseInt(newDailyLimit, 10) : undefined,
        label: newLabel || undefined,
      });
      setShowAdd(false); setNewProvider(''); setNewRawKey(''); setNewPriority('0'); setNewDailyLimit(''); setNewLabel('');
      await fetchData();
    } catch (e) { setError(getParsedApiError(e)); }
    finally { setAddLoading(false); }
  };

  const handleDeactivate = async (keyId: number) => {
    if (!confirm('确定停用此 Key？')) return;
    try { await adminApi.deactivateKey(keyId); await fetchData(); } catch (e) { setError(getParsedApiError(e)); }
  };

  return (
    <div className="min-h-screen px-4 pb-6 pt-4 md:px-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">平台 API Key 管理</h1>
          <p className="text-sm text-secondary">仅 super_admin 可操作</p>
        </div>
        <button type="button" onClick={() => setShowAdd(true)} className="btn-primary text-sm">
          + 添加 Key
        </button>
      </header>

      {error && <ApiErrorAlert error={error} className="mb-4" />}

      {/* Usage stats cards */}
      {usageStats.length > 0 && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {usageStats.map((s) => (
            <div key={s.provider} className="rounded-2xl border border-white/8 bg-card/60 p-4 backdrop-blur-sm">
              <p className="text-xs text-muted">{s.provider}</p>
              <p className="mt-1 text-lg font-bold text-white">{s.active_keys} 个活跃</p>
              <p className="text-xs text-secondary">
                今日 {s.total_used_today}{s.total_daily_limit > 0 ? ` / ${s.total_daily_limit}` : ''}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Keys table */}
      <div className="overflow-x-auto rounded-2xl border border-white/8 bg-card/60 backdrop-blur-sm">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
          </div>
        ) : keys.length === 0 ? (
          <div className="py-12 text-center text-sm text-secondary">暂无 Key，点击上方按钮添加</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/8 text-left text-xs text-muted">
                <th className="p-3">ID</th><th className="p-3">Provider</th><th className="p-3">标签</th>
                <th className="p-3">Key</th><th className="p-3">优先级</th><th className="p-3">今日用量</th>
                <th className="p-3">状态</th><th className="p-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-white/5 text-secondary">
                  <td className="p-3">{k.id}</td>
                  <td className="p-3 text-white">{k.provider}</td>
                  <td className="p-3">{k.label || '—'}</td>
                  <td className="p-3 font-mono text-xs">{k.key_preview}</td>
                  <td className="p-3">{k.priority}</td>
                  <td className="p-3">{k.used_today}{k.daily_limit ? ` / ${k.daily_limit}` : ''}</td>
                  <td className="p-3">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${k.is_active ? 'bg-emerald-400/10 text-emerald-400' : 'bg-danger/10 text-danger'}`}>
                      {k.is_active ? '活跃' : '停用'}
                    </span>
                  </td>
                  <td className="p-3">
                    {k.is_active && (
                      <button type="button" onClick={() => handleDeactivate(k.id)}
                        className="rounded px-2 py-1 text-xs text-danger hover:bg-danger/10">停用</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Add key modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setShowAdd(false)}>
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative w-96 rounded-2xl bg-base border border-white/10 p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-white mb-4">添加平台 API Key</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-muted">Provider</label>
                <select value={newProvider} onChange={(e) => setNewProvider(e.target.value)} className="input-terminal w-full mt-1">
                  <option value="">选择...</option>
                  {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted">API Key</label>
                <input type="password" value={newRawKey} onChange={(e) => setNewRawKey(e.target.value)}
                  placeholder="sk-..." className="input-terminal w-full mt-1" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted">优先级</label>
                  <input type="number" value={newPriority} onChange={(e) => setNewPriority(e.target.value)} className="input-terminal w-full mt-1" />
                </div>
                <div>
                  <label className="text-xs text-muted">日限额（留空=无限）</label>
                  <input type="number" value={newDailyLimit} onChange={(e) => setNewDailyLimit(e.target.value)} className="input-terminal w-full mt-1" />
                </div>
              </div>
              <div>
                <label className="text-xs text-muted">标签（可选）</label>
                <input type="text" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="团队测试Key" className="input-terminal w-full mt-1" />
              </div>
            </div>
            <div className="mt-4 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowAdd(false)} className="btn-secondary text-sm">取消</button>
              <button type="button" onClick={handleAdd} disabled={!newProvider || !newRawKey || addLoading} className="btn-primary text-sm">
                {addLoading ? '添加中...' : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminKeysPage;

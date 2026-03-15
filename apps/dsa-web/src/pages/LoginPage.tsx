import type React from 'react';
import { useState } from 'react';
import { ApiErrorAlert } from '../components/common';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ParsedApiError } from '../api/error';
import { isParsedApiError } from '../api/error';
import { useAuth } from '../hooks';
import { SettingsAlert } from '../components/settings';

const LoginPage: React.FC = () => {
  const { login, saasLogin, saasRegister, passwordSet, saasMode } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const rawRedirect = searchParams.get('redirect') ?? '';
  const redirect =
    rawRedirect.startsWith('/') && !rawRedirect.startsWith('//') ? rawRedirect : '/';

  // Form state
  const [email, setEmail] = useState('');
  const [nickname, setNickname] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | ParsedApiError | null>(null);
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // Legacy admin mode: first-time password setup
  const isFirstTime = !saasMode && !passwordSet;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (saasMode) {
      // SaaS mode: email + password login/register
      if (!email.trim()) {
        setError('请输入邮箱');
        return;
      }
      if (!password.trim()) {
        setError('请输入密码');
        return;
      }
      if (isRegisterMode && password !== passwordConfirm) {
        setError('两次输入的密码不一致');
        return;
      }

      setIsSubmitting(true);
      try {
        const result = isRegisterMode
          ? await saasRegister(email, password, nickname || undefined)
          : await saasLogin(email, password);

        if (result.success) {
          navigate(redirect, { replace: true });
        } else {
          setError(result.error ?? '操作失败');
        }
      } finally {
        setIsSubmitting(false);
      }
    } else {
      // Legacy admin mode
      if (isFirstTime && password !== passwordConfirm) {
        setError('两次输入的密码不一致');
        return;
      }
      setIsSubmitting(true);
      try {
        const result = await login(password, isFirstTime ? passwordConfirm : undefined);
        if (result.success) {
          navigate(redirect, { replace: true });
        } else {
          setError(result.error ?? '登录失败');
        }
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const toggleMode = () => {
    setIsRegisterMode(!isRegisterMode);
    setError(null);
  };

  // Page titles
  const getTitle = () => {
    if (saasMode) return isRegisterMode ? '创建账号' : '用户登录';
    return isFirstTime ? '设置初始密码' : '管理员登录';
  };

  const getSubtitle = () => {
    if (saasMode) {
      return isRegisterMode
        ? '注册后享受 7 天免费试用'
        : '请输入邮箱和密码登录';
    }
    return isFirstTime ? '请设置管理员密码，输入两遍确认' : '请输入密码以继续访问';
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-base px-4">
      <div className="w-full max-w-sm rounded-2xl border border-white/8 bg-card/80 p-6 backdrop-blur-sm">
        <h1 className="mb-2 text-xl font-semibold text-white">
          {getTitle()}
        </h1>
        <p className="mb-6 text-sm text-secondary">
          {getSubtitle()}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email field (SaaS mode only) */}
          {saasMode ? (
            <div>
              <label htmlFor="email" className="mb-1 block text-sm font-medium text-secondary">
                邮箱
              </label>
              <input
                id="email"
                type="email"
                className="input-terminal"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isSubmitting}
                autoFocus
                autoComplete="email"
              />
            </div>
          ) : null}

          {/* Nickname (SaaS register only) */}
          {saasMode && isRegisterMode ? (
            <div>
              <label htmlFor="nickname" className="mb-1 block text-sm font-medium text-secondary">
                昵称（可选）
              </label>
              <input
                id="nickname"
                type="text"
                className="input-terminal"
                placeholder="您的昵称"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                disabled={isSubmitting}
                autoComplete="nickname"
              />
            </div>
          ) : null}

          {/* Password */}
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-secondary">
              {isFirstTime ? '新密码' : '密码'}
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                className="input-terminal pr-10"
                placeholder={isFirstTime ? '输入新密码' : '输入密码'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                autoFocus={!saasMode}
                autoComplete={isFirstTime || isRegisterMode ? 'new-password' : 'current-password'}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-secondary hover:text-white transition-colors"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                )}
              </button>
            </div>
          </div>

          {/* Confirm password (register or first-time) */}
          {isFirstTime || (saasMode && isRegisterMode) ? (
            <div>
              <label
                htmlFor="passwordConfirm"
                className="mb-1 block text-sm font-medium text-secondary"
              >
                确认密码
              </label>
              <div className="relative">
                <input
                  id="passwordConfirm"
                  type={showConfirm ? 'text' : 'password'}
                  className="input-terminal pr-10"
                  placeholder="再次输入密码"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-secondary hover:text-white transition-colors"
                  onClick={() => setShowConfirm(!showConfirm)}
                  tabIndex={-1}
                  aria-label={showConfirm ? 'Hide password' : 'Show password'}
                >
                  {showConfirm ? (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  )}
                </button>
              </div>
            </div>
          ) : null}

          {/* Error display */}
          {error
            ? isParsedApiError(error)
              ? <ApiErrorAlert error={error} className="!mt-3" />
              : (
                <SettingsAlert
                  title={isRegisterMode ? '注册失败' : '登录失败'}
                  message={error}
                  variant="error"
                  className="!mt-3"
                />
              )
            : null}

          {/* Submit button */}
          <button
            type="submit"
            className="btn-primary w-full"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? (isRegisterMode ? '注册中...' : isFirstTime ? '设置中...' : '登录中...')
              : (isRegisterMode ? '注册' : isFirstTime ? '设置密码' : '登录')}
          </button>

          {/* Toggle register/login (SaaS mode only) */}
          {saasMode ? (
            <div className="text-center">
              <button
                type="button"
                className="text-sm text-accent hover:text-accent/80 transition-colors"
                onClick={toggleMode}
              >
                {isRegisterMode ? '已有账号？去登录' : '没有账号？立即注册'}
              </button>
            </div>
          ) : null}
        </form>
      </div>
    </div>
  );
};

export default LoginPage;

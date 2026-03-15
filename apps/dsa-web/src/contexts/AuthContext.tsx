import type React from 'react';
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { createParsedApiError, getParsedApiError, type ParsedApiError } from '../api/error';
import { authApi, type SaasLoginResponse, type SaasProfileResponse } from '../api/auth';
import { setAccessToken, getAccessToken } from '../api/index';

type AuthContextValue = {
  // Common
  authEnabled: boolean;
  loggedIn: boolean;
  isLoading: boolean;
  loadError: ParsedApiError | null;
  logout: () => Promise<void>;
  refreshStatus: () => Promise<void>;

  // Legacy admin mode
  passwordSet: boolean;
  passwordChangeable: boolean;
  login: (password: string, passwordConfirm?: string) => Promise<{ success: boolean; error?: ParsedApiError }>;
  changePassword: (
    currentPassword: string,
    newPassword: string,
    newPasswordConfirm: string
  ) => Promise<{ success: boolean; error?: ParsedApiError }>;

  // SaaS mode
  saasMode: boolean;
  user: SaasProfileResponse | null;
  saasLogin: (email: string, password: string) => Promise<{ success: boolean; error?: ParsedApiError }>;
  saasRegister: (
    email: string,
    password: string,
    nickname?: string
  ) => Promise<{ success: boolean; error?: ParsedApiError }>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function extractLoginError(err: unknown): ParsedApiError {
  const parsed = getParsedApiError(err);
  if (parsed.status === 429) {
    return createParsedApiError({
      title: '登录尝试过于频繁',
      message: '尝试次数过多，请稍后再试。',
      rawMessage: parsed.rawMessage,
      status: parsed.status,
      category: parsed.category,
    });
  }
  return parsed;
}

// Auto-refresh access token every 12 minutes (token expires in 15 min)
const TOKEN_REFRESH_INTERVAL_MS = 12 * 60 * 1000;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [passwordSet, setPasswordSet] = useState(false);
  const [passwordChangeable, setPasswordChangeable] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<ParsedApiError | null>(null);
  const [saasMode, setSaasMode] = useState(false);
  const [user, setUser] = useState<SaasProfileResponse | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start periodic token refresh
  const startTokenRefresh = useCallback(() => {
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    refreshTimerRef.current = setInterval(async () => {
      if (!getAccessToken()) return;
      try {
        const result = await authApi.refreshToken();
        setAccessToken(result.access_token);
      } catch {
        // Token refresh failed — force re-login
        setAccessToken(null);
        setLoggedIn(false);
        setUser(null);
      }
    }, TOKEN_REFRESH_INTERVAL_MS);
  }, []);

  const stopTokenRefresh = useCallback(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const status = await authApi.getStatus();
      setAuthEnabled(status.authEnabled);
      setLoggedIn(status.loggedIn);
      setPasswordSet(status.passwordSet ?? false);
      setPasswordChangeable(status.passwordChangeable ?? false);
      setSaasMode(status.saasMode ?? false);

      // If SaaS mode, attempt to restore session from refresh token cookie
      if (status.saasMode) {
        let token = getAccessToken();

        // No in-memory token — try to get one from the refresh token cookie
        if (!token) {
          try {
            const result = await authApi.refreshToken();
            setAccessToken(result.access_token);
            token = result.access_token;
            startTokenRefresh();
          } catch {
            // No valid refresh token cookie — user must log in
          }
        }

        if (token) {
          try {
            const profile = await authApi.getProfile();
            setUser(profile);
            setLoggedIn(true);
          } catch {
            // Token might be expired
            setAccessToken(null);
            setLoggedIn(false);
          }
        }
      }
    } catch (err) {
      setLoadError(getParsedApiError(err));
      setAuthEnabled(false);
      setLoggedIn(false);
      setPasswordSet(false);
      setPasswordChangeable(false);
    } finally {
      setIsLoading(false);
    }
  }, [startTokenRefresh]);

  useEffect(() => {
    void fetchStatus();
    return () => stopTokenRefresh();
  }, [fetchStatus, stopTokenRefresh]);

  // Handle SaaS login response common logic
  const handleSaasAuth = useCallback(
    (result: SaasLoginResponse) => {
      setAccessToken(result.access_token);
      setLoggedIn(true);
      setUser({
        user_id: result.user_id,
        uuid: '',
        email: result.email,
        nickname: result.nickname,
        role: result.role,
        tier: result.tier,
        watchlist_limit: 3,
      });
      startTokenRefresh();
    },
    [startTokenRefresh]
  );

  // Legacy admin login
  const login = useCallback(
    async (
      password: string,
      passwordConfirm?: string
    ): Promise<{ success: boolean; error?: ParsedApiError }> => {
      try {
        await authApi.login(password, passwordConfirm);
        setLoggedIn(true);
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: extractLoginError(err) };
      }
    },
    []
  );

  // SaaS login
  const saasLogin = useCallback(
    async (email: string, password: string): Promise<{ success: boolean; error?: ParsedApiError }> => {
      try {
        const result = await authApi.saasLogin(email, password);
        handleSaasAuth(result);
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: extractLoginError(err) };
      }
    },
    [handleSaasAuth]
  );

  // SaaS register
  const saasRegister = useCallback(
    async (
      email: string,
      password: string,
      nickname?: string
    ): Promise<{ success: boolean; error?: ParsedApiError }> => {
      try {
        const result = await authApi.register(email, password, nickname);
        handleSaasAuth(result);
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: extractLoginError(err) };
      }
    },
    [handleSaasAuth]
  );

  const changePassword = useCallback(
    async (
      currentPassword: string,
      newPassword: string,
      newPasswordConfirm: string
    ): Promise<{ success: boolean; error?: ParsedApiError }> => {
      try {
        await authApi.changePassword(currentPassword, newPassword, newPasswordConfirm);
        return { success: true };
      } catch (err: unknown) {
        return { success: false, error: getParsedApiError(err) };
      }
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setLoggedIn(false);
      setUser(null);
      stopTokenRefresh();
    }
  }, [stopTokenRefresh]);

  return (
    <AuthContext.Provider
      value={{
        authEnabled,
        loggedIn,
        passwordSet,
        passwordChangeable,
        isLoading,
        loadError,
        login,
        changePassword,
        logout,
        refreshStatus: fetchStatus,
        saasMode,
        user,
        saasLogin,
        saasRegister,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- useAuth is a hook, co-located for context access
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}

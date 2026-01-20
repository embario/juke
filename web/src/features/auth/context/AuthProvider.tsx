import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { loginRequest, logoutRequest, registerRequest } from '../api/authApi';
import type { AuthContextValue, AuthState, LoginPayload, RegisterPayload } from '../types';

const STORAGE_KEY = 'juke-auth-state';

const defaultState: AuthState = {
  token: null,
  username: null,
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

type Props = {
  children: ReactNode;
};

const readStateFromStorage = (): AuthState => {
  if (typeof window === 'undefined') {
    return defaultState;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultState;
    }
    return JSON.parse(raw) as AuthState;
  } catch (error) {
    return defaultState;
  }
};

export const AuthProvider = ({ children }: Props) => {
  const [state, setState] = useState<AuthState>(() => readStateFromStorage());

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (!state.token) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await loginRequest(payload);
    setState({ token: response.token, username: payload.username });
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    await registerRequest(payload);
  }, []);

  const logout = useCallback(() => {
    const activeToken = state.token;
    setState(defaultState);
    if (activeToken) {
      void logoutRequest(activeToken).catch((error) => {
        if (import.meta.env.DEV) {
          // Best-effort session cleanup; ignore errors in production.
          console.error('Failed to revoke session', error);
        }
      });
    }
  }, [state.token]);

  const value = useMemo<AuthContextValue>(() => ({
    ...state,
    login,
    register,
    logout,
    isAuthenticated: Boolean(state.token),
  }), [login, logout, register, state]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuthContext = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuthContext must be used inside AuthProvider');
  }
  return ctx;
};

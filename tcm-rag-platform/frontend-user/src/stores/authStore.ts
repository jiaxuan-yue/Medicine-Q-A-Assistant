import { create } from 'zustand';
import { authApi } from '../api/auth';
import type { User, LoginRequest, RegisterRequest } from '../types';
import { useCaseProfilesStore } from './caseProfilesStore';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  loading: boolean;

  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  setTokens: (accessToken: string, refreshToken: string) => void;
  refreshAccessToken: () => Promise<void>;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  loading: false,

  login: async (data: LoginRequest) => {
    set({ loading: true });
    try {
      const res = await authApi.login(data);
      const tokens = res.data.data;
      useCaseProfilesStore.getState().reset();
      sessionStorage.setItem('access_token', tokens.access_token);
      sessionStorage.setItem('refresh_token', tokens.refresh_token);
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        isAuthenticated: true,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  register: async (data: RegisterRequest) => {
    set({ loading: true });
    try {
      const res = await authApi.register(data);
      const tokens = res.data.data;
      useCaseProfilesStore.getState().reset();
      sessionStorage.setItem('access_token', tokens.access_token);
      sessionStorage.setItem('refresh_token', tokens.refresh_token);
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        isAuthenticated: true,
        loading: false,
      });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore
    }
    useCaseProfilesStore.getState().reset();
    sessionStorage.clear();
    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  },

  setTokens: (accessToken: string, refreshToken: string) => {
    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    set({ accessToken, refreshToken, isAuthenticated: true });
  },

  refreshAccessToken: async () => {
    const { refreshToken } = get();
    if (!refreshToken) return;
    try {
      const res = await authApi.refresh(refreshToken);
      const tokens = res.data.data;
      sessionStorage.setItem('access_token', tokens.access_token);
      sessionStorage.setItem('refresh_token', tokens.refresh_token);
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
    } catch {
      sessionStorage.clear();
      set({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
      });
    }
  },

  hydrate: () => {
    const accessToken = sessionStorage.getItem('access_token');
    const refreshToken = sessionStorage.getItem('refresh_token');
    if (accessToken && refreshToken) {
      set({ accessToken, refreshToken, isAuthenticated: true });
    }
  },
}));

import { create } from 'zustand';
import type { User } from '../types';
import { authApi } from '../api/auth';
import { setToken, setRefreshToken, clearTokens, getToken } from '../utils';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: !!getToken(),
  loading: false,

  login: async (username: string, password: string) => {
    set({ loading: true });
    try {
      const { data } = await authApi.login(username, password);
      const { access_token, refresh_token, user } = data.data;
      setToken(access_token);
      setRefreshToken(refresh_token);
      set({ user, isAuthenticated: true, loading: false });
    } catch (error) {
      set({ loading: false });
      throw error;
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } finally {
      clearTokens();
      set({ user: null, isAuthenticated: false });
    }
  },

  checkAuth: async () => {
    const token = getToken();
    if (!token) {
      set({ isAuthenticated: false, user: null });
      return;
    }
    try {
      const { data } = await authApi.me();
      set({ user: data.data, isAuthenticated: true });
    } catch {
      clearTokens();
      set({ user: null, isAuthenticated: false });
    }
  },
}));

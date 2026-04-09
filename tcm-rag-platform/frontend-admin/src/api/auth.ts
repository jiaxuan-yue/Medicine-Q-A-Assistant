import client from './client';
import type { ApiResponse, LoginResponse } from '../types';

export const authApi = {
  login: (username: string, password: string) =>
    client.post<ApiResponse<LoginResponse>>('/auth/login', { username, password }),

  refresh: (refreshToken: string) =>
    client.post<ApiResponse<{ access_token: string }>>('/auth/refresh', {
      refresh_token: refreshToken,
    }),

  logout: () => client.post('/auth/logout'),

  me: () => client.get<ApiResponse<LoginResponse['user']>>('/auth/me'),
};

import client from './client';
import type { ApiResponse, AuthTokens, LoginRequest, RegisterRequest } from '../types';

export const authApi = {
  login: (data: LoginRequest) =>
    client.post<ApiResponse<AuthTokens>>('/auth/login', data),

  register: (data: RegisterRequest) =>
    client.post<ApiResponse<AuthTokens>>('/auth/register', data),

  refresh: (refreshToken: string) =>
    client.post<ApiResponse<AuthTokens>>('/auth/refresh', {
      refresh_token: refreshToken,
    }),

  logout: () => client.post('/auth/logout'),
};

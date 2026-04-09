import client from './client';
import type { ApiResponse, PaginatedResponse, User } from '../types';

export const userApi = {
  list: (params: { page?: number; size?: number; role?: string }) =>
    client.get<ApiResponse<PaginatedResponse<User>>>('/admin/users', { params }),

  updateRole: (userId: number, role: string) =>
    client.put<ApiResponse<User>>(`/admin/users/${userId}/role`, { role }),
};

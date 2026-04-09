import client from './client';
import type { ApiResponse, DashboardStats } from '../types';

export const adminApi = {
  getDashboardStats: () =>
    client.get<ApiResponse<DashboardStats>>('/admin/dashboard/stats'),
};

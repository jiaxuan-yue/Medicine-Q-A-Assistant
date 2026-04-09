import client from './client';
import type { ApiResponse, PaginatedResponse, FeedbackItem, FeedbackStats } from '../types';

export const feedbackApi = {
  list: (params?: { page?: number; size?: number }) =>
    client.get<ApiResponse<PaginatedResponse<FeedbackItem>>>('/feedback/', { params }),

  getStats: () =>
    client.get<ApiResponse<FeedbackStats>>('/feedback/stats'),

  getDetail: (id: number) =>
    client.get<ApiResponse<FeedbackItem>>(`/feedback/${id}`),
};

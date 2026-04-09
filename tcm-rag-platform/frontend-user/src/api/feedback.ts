import client from './client';
import type { ApiResponse, FeedbackData } from '../types';

export const feedbackApi = {
  submit: (data: FeedbackData) =>
    client.post<ApiResponse<{ id: number }>>('/feedback/', data),

  listMine: (page = 1, size = 20) =>
    client.get<ApiResponse<{ items: FeedbackData[]; total: number }>>('/feedback/', {
      params: { page, size },
    }),
};

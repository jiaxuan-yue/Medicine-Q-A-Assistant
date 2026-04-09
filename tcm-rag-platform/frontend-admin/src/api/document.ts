import client from './client';
import type { ApiResponse, PaginatedResponse, Document } from '../types';

export const documentApi = {
  list: (params: { page?: number; size?: number; status?: string }) =>
    client.get<ApiResponse<PaginatedResponse<Document>>>('/documents', { params }),

  upload: (formData: FormData) =>
    client.post<ApiResponse<Document>>('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  getDetail: (docId: string) =>
    client.get<ApiResponse<Document>>(`/documents/${docId}`),

  review: (docId: string, action: 'approve' | 'reject', comment?: string) =>
    client.post(`/admin/documents/${docId}/review`, { action, comment }),
};

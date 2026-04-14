import client from './client';
import type { ApiResponse, ChatSession, Message } from '../types';

export const chatApi = {
  createSession: (payload: { title?: string; case_profile_id: number }) =>
    client.post<ApiResponse<ChatSession>>('/chats', payload),

  listSessions: (page?: number, size?: number) =>
    client.get<ApiResponse<{ items: ChatSession[]; total: number }>>('/chats', {
      params: { page, size },
    }),

  getMessages: (sessionId: string) =>
    client.get<ApiResponse<Message[]>>(`/chats/${sessionId}/messages`),
};

export interface User {
  id: number;
  username: string;
  email: string;
  role: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ChatSession {
  session_id: string;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  latency_ms?: number;
  created_at: string;
}

export interface Citation {
  doc_id: string;
  doc_title: string;
  excerpt: string;
  chunk_id?: string;
  location?: string;
  /** @deprecated use excerpt instead */
  text?: string;
}

export interface FeedbackData {
  message_id: number;
  feedback_type: 'like' | 'dislike' | 'correction' | 'badcase' | 'followup';
  content?: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  trace_id: string;
}

// SSE event types
export interface SSEStartEvent {
  session_id: string;
  message_id: string;
}

export interface SSEChunkEvent {
  content: string;
}

export interface SSECitationEvent {
  citations: Citation[];
}

export interface SSEDoneEvent {
  total_tokens: number;
  latency_ms: number;
}

export interface SSEErrorEvent {
  code: string;
  message: string;
}

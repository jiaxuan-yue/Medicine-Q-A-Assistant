import { create } from 'zustand';
import { chatApi } from '../api/chat';
import type { ChatSession, Message, Citation } from '../types';

interface ChatState {
  sessions: ChatSession[];
  currentSession: ChatSession | null;
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
  streamingCitations: Citation[];
  loading: boolean;

  loadSessions: (page?: number, size?: number) => Promise<void>;
  createSession: () => Promise<ChatSession>;
  selectSession: (session: ChatSession) => void;
  loadMessages: (sessionId: string) => Promise<void>;
  appendStreamChunk: (content: string) => void;
  setStreamingCitations: (citations: Citation[]) => void;
  finishStream: (messageId: string) => void;
  setStreaming: (streaming: boolean) => void;
  addUserMessage: (content: string) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  streamingCitations: [],
  loading: false,

  loadSessions: async (page = 1, size = 50) => {
    set({ loading: true });
    try {
      const res = await chatApi.listSessions(page, size);
      set({ sessions: res.data.data.items, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  createSession: async () => {
    const res = await chatApi.createSession();
    const session = res.data.data;
    set((state) => ({
      sessions: [session, ...state.sessions],
      currentSession: session,
      messages: [],
    }));
    return session;
  },

  selectSession: (session: ChatSession) => {
    set({ currentSession: session, messages: [], streamingContent: '' });
  },

  loadMessages: async (sessionId: string) => {
    set({ loading: true });
    try {
      const res = await chatApi.getMessages(sessionId);
      set({ messages: res.data.data, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  appendStreamChunk: (content: string) => {
    set((state) => ({
      streamingContent: state.streamingContent + content,
    }));
  },

  setStreamingCitations: (citations: Citation[]) => {
    set({ streamingCitations: citations });
  },

  finishStream: (messageId: string) => {
    const { streamingContent, streamingCitations } = get();
    const assistantMessage: Message = {
      id: messageId,
      role: 'assistant',
      content: streamingContent,
      citations: streamingCitations.length > 0 ? streamingCitations : undefined,
      created_at: new Date().toISOString(),
    };
    set((state) => ({
      messages: [...state.messages, assistantMessage],
      isStreaming: false,
      streamingContent: '',
      streamingCitations: [],
    }));
  },

  setStreaming: (streaming: boolean) => {
    set({ isStreaming: streaming, streamingContent: '', streamingCitations: [] });
  },

  addUserMessage: (content: string) => {
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    set((state) => ({
      messages: [...state.messages, userMessage],
    }));
  },
}));

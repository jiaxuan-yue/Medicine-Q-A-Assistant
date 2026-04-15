import { useCallback, useRef, useState } from 'react';
import { connectSSE } from '../utils/sse';
import { useChatStore } from '../stores/chatStore';
import type { Citation, UserLocationPayload } from '../types';

interface UseSSEReturn {
  isStreaming: boolean;
  streamContent: string;
  citations: Citation[];
  error: string | null;
  sendMessage: (sessionId: string, query: string, userLocation?: UserLocationPayload | null) => Promise<void>;
  cancelStream: () => void;
}

export function useSSE(): UseSSEReturn {
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const messageIdRef = useRef<string>('');

  const {
    isStreaming,
    streamingContent,
    streamingCitations,
    setStreaming,
    appendStreamChunk,
    setStreamingCitations,
    finishStream,
    addUserMessage,
  } = useChatStore();

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const sendMessage = useCallback(
    async (sessionId: string, query: string, userLocation: UserLocationPayload | null = null) => {
      if (isStreaming) return;

      setError(null);
      addUserMessage(query);
      setStreaming(true);

      const abortController = new AbortController();
      abortRef.current = abortController;

      let receivedDone = false;

      try {
        await connectSSE(
          sessionId,
          query,
          userLocation,
          {
            onStart: (data) => {
              messageIdRef.current = data.message_id;
            },
            onChunk: (data) => {
              appendStreamChunk(data.content);
            },
            onCitation: (data) => {
              setStreamingCitations(data.citations);
            },
            onDone: (data) => {
              receivedDone = true;
              finishStream(
                data.message_id || messageIdRef.current || `msg-${Date.now()}`,
                data.message_kind || 'answer',
              );
            },
            onError: (data) => {
              receivedDone = true;
              setError(data.message);
              setStreaming(false);
            },
          },
          abortController.signal,
        );

        // Safety: if stream ended without a done/error event, finalize anyway
        if (!receivedDone) {
          finishStream(messageIdRef.current || `msg-${Date.now()}`, 'answer');
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError((err as Error).message || '发送消息失败');
          setStreaming(false);
        }
      }
    },
    [isStreaming, addUserMessage, setStreaming, appendStreamChunk, setStreamingCitations, finishStream],
  );

  return {
    isStreaming,
    streamContent: streamingContent,
    citations: streamingCitations,
    error,
    sendMessage,
    cancelStream,
  };
}

import { useCallback, useRef, useState } from 'react';
import { connectSSE } from '../utils/sse';
import { useChatStore } from '../stores/chatStore';
import type { Citation } from '../types';

interface UseSSEReturn {
  isStreaming: boolean;
  streamContent: string;
  citations: Citation[];
  error: string | null;
  sendMessage: (sessionId: string, query: string) => Promise<void>;
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
    async (sessionId: string, query: string) => {
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
            onDone: () => {
              receivedDone = true;
              finishStream(messageIdRef.current || `msg-${Date.now()}`);
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
          finishStream(messageIdRef.current || `msg-${Date.now()}`);
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

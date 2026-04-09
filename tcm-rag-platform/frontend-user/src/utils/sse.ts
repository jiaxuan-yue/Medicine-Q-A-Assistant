import type {
  SSEStartEvent,
  SSEChunkEvent,
  SSECitationEvent,
  SSEDoneEvent,
  SSEErrorEvent,
} from '../types';

export interface SSECallbacks {
  onStart?: (data: SSEStartEvent) => void;
  onChunk?: (data: SSEChunkEvent) => void;
  onCitation?: (data: SSECitationEvent) => void;
  onDone?: (data: SSEDoneEvent) => void;
  onError?: (data: SSEErrorEvent) => void;
}

export async function connectSSE(
  sessionId: string,
  query: string,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = sessionStorage.getItem('access_token');

  const response = await fetch(`/api/v1/chats/${sessionId}/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  // Persist currentEvent across chunk reads so split event:/data: lines still pair up
  let currentEvent = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          const dataStr = line.slice(5).trim();
          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);
            switch (currentEvent) {
              case 'start':
                callbacks.onStart?.(data as SSEStartEvent);
                break;
              case 'chunk':
                callbacks.onChunk?.(data as SSEChunkEvent);
                break;
              case 'citation':
                callbacks.onCitation?.(data as SSECitationEvent);
                break;
              case 'done':
                callbacks.onDone?.(data as SSEDoneEvent);
                break;
              case 'error':
                callbacks.onError?.(data as SSEErrorEvent);
                break;
            }
          } catch (e) {
            console.error('[SSE] Failed to parse event data:', dataStr, e);
          }
          // Reset after processing a data line so stale event names don't leak
          currentEvent = '';
        } else if (line.trim() === '') {
          // Empty line marks end of an SSE event block — reset event name
          currentEvent = '';
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

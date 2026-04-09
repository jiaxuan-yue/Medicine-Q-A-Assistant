// TODO: Phase 3 - WebSocket notification hook for real-time admin alerts
import { useEffect, useRef } from 'react';

export function useWebSocket(_url: string) {
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Stub: WebSocket connection will be implemented in Phase 3
    return () => {
      wsRef.current?.close();
    };
  }, [_url]);

  return { ws: wsRef.current, connected: false };
}

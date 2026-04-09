import React, { useEffect, useRef } from 'react';
import { Spin } from 'antd';
import MessageBubble from './MessageBubble';
import type { Message } from '../types';
import './ChatWindow.css';

interface ChatWindowProps {
  messages: Message[];
  isStreaming: boolean;
  streamContent: string;
  loading?: boolean;
}

const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  isStreaming,
  streamContent,
  loading = false,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamContent]);

  if (loading) {
    return (
      <div className="chat-window-loading">
        <Spin size="large" tip="加载消息中..." />
      </div>
    );
  }

  return (
    <div className="chat-window">
      {messages.length === 0 && !isStreaming && (
        <div className="chat-empty">
          <div className="chat-empty-icon">🏥</div>
          <h3>中医智能问诊</h3>
          <p>请输入您的问题，AI将基于中医古籍为您解答</p>
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isStreaming && (
        <MessageBubble
          message={{
            id: 'streaming',
            role: 'assistant',
            content: '',
            created_at: new Date().toISOString(),
          }}
          isStreaming
          streamContent={streamContent}
        />
      )}
      <div ref={bottomRef} />
    </div>
  );
};

export default ChatWindow;

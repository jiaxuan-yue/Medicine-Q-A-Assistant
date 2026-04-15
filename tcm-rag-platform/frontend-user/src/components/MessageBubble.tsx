import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Message } from '../types';
import FeedbackActions from './FeedbackActions';
import CitationPanel from './CitationPanel';
import './MessageBubble.css';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
  streamContent?: string;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  isStreaming = false,
  streamContent,
}) => {
  const isUser = message.role === 'user';
  const isFollowup = message.kind === 'followup';
  const content = isStreaming ? (streamContent || '') : message.content;

  // Parse messageId as number for feedback API (strip non-numeric prefix)
  const numericId = parseInt(message.id, 10);
  const hasValidId = !isNaN(numericId) && !isStreaming;

  return (
    <div className={`message-bubble ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-meta-line">
        <div className="message-role-chip">
          {isUser ? '我的问题' : isFollowup ? '追问助手' : '知识助手'}
        </div>
        <div className="message-time">
          {new Date(message.created_at).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
      <div className="bubble-shell">
        <div className={`bubble ${isUser ? 'bubble-user' : 'bubble-assistant'}`}>
          <div className="bubble-content">
            {isUser ? (
              content
            ) : (
              <div className="markdown-body">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                  components={{
                    a: ({ href, children, ...props }) => (
                      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                        {children}
                      </a>
                    ),
                    code: ({ className, children, ...props }) => {
                      const isInline = !className;
                      return isInline ? (
                        <code className="inline-code" {...props}>{children}</code>
                      ) : (
                        <code className={className} {...props}>{children}</code>
                      );
                    },
                  }}
                >
                  {content}
                </ReactMarkdown>
                {isStreaming && <span className="typing-cursor">|</span>}
              </div>
            )}
            {isUser && isStreaming && <span className="typing-cursor">|</span>}
          </div>
          {!isUser && !isStreaming && message.citations && message.citations.length > 0 && (
            <CitationPanel citations={message.citations} />
          )}
          {!isUser && !isFollowup && hasValidId && (
            <FeedbackActions messageId={numericId} />
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;

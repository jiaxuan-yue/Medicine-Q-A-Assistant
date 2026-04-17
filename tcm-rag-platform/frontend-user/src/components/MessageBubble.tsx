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
  const content = isStreaming ? (streamContent || '') : message.content;
  const isFollowup = message.kind === 'followup';
  const isFollowupCard = !isUser && (
    isFollowup || /^第\s*\d+\s*问\s*\/\s*共\s*\d+\s*问/.test(content.trim())
  );

  // Parse messageId as number for feedback API (strip non-numeric prefix)
  const numericId = parseInt(message.id, 10);
  const hasValidId = !isNaN(numericId) && !isStreaming;
  const followupMetaMatch = content.trim().match(/^第\s*(\d+)\s*问\s*\/\s*共\s*(\d+)\s*问/);
  const followupLines = content
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const followupQuestion = followupMetaMatch
    ? (followupLines[1] || '')
    : (followupLines[0] || content);
  const followupHint = followupMetaMatch
    ? followupLines.slice(2).join(' ')
    : followupLines.slice(1).join(' ');
  const followupCurrent = followupMetaMatch ? Number(followupMetaMatch[1]) : 0;
  const followupTotal = followupMetaMatch ? Number(followupMetaMatch[2]) : 0;

  return (
    <div className={`message-bubble ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-meta-line">
        <div className="message-role-chip">
          {isUser ? '我的问题' : isFollowupCard ? '追问助手' : '知识助手'}
        </div>
        <div className="message-time">
          {new Date(message.created_at).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </div>
      </div>
      <div className="bubble-shell">
        <div className={`bubble ${isUser ? 'bubble-user' : 'bubble-assistant'} ${isFollowupCard ? 'bubble-followup' : ''}`}>
          <div className="bubble-content">
            {isUser ? content : isFollowupCard ? (
              <div className="followup-card">
                <div className="followup-card-topline">
                  <span className="followup-card-badge">继续补充</span>
                  {followupMetaMatch && <span className="followup-card-progress">{followupMetaMatch[0]}</span>}
                </div>
                <div className="followup-card-question">
                  {followupQuestion}
                  {isStreaming && !followupQuestion && <span className="typing-cursor">|</span>}
                </div>
                {(followupHint || (isStreaming && content)) && (
                  <div className="followup-card-hint">
                    {followupHint || '正在整理下一步追问...'}
                    {isStreaming && <span className="typing-cursor">|</span>}
                  </div>
                )}
                {followupTotal > 0 && (
                  <div className="followup-card-steps" aria-hidden="true">
                    {Array.from({ length: followupTotal }, (_, index) => (
                      <span
                        key={index}
                        className={`followup-card-step ${index < followupCurrent ? 'is-active' : ''}`}
                      />
                    ))}
                  </div>
                )}
              </div>
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
          </div>
          {isUser && isStreaming && <span className="typing-cursor">|</span>}
          {!isUser && !isStreaming && message.citations && message.citations.length > 0 && (
            <CitationPanel citations={message.citations} />
          )}
          {!isUser && !isFollowupCard && hasValidId && (
            <FeedbackActions messageId={numericId} />
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;

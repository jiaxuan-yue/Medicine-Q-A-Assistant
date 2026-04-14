import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Input, Button, Layout, Typography, Image, message } from 'antd';
import { SendOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useChatStore } from '../stores/chatStore';
import { useSSE } from '../hooks/useSSE';
import ChatWindow from '../components/ChatWindow';
import UploadImagePanel from '../components/UploadImagePanel';
import { getApiErrorMessage } from '../utils/apiError';
import './ChatDetail.css';

const { Header, Content, Footer } = Layout;
const { Title } = Typography;
const { TextArea } = Input;

const ChatDetail: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState('');
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const { sessions, messages, loading, loadMessages, loadSessions, isStreaming, streamingContent } =
    useChatStore();
  const { sendMessage, error, cancelStream } = useSSE();
  const currentSession = sessions.find((item) => item.session_id === sessionId);

  useEffect(() => {
    if (sessions.length === 0) {
      loadSessions().catch(() => {
        // Ignore session list failures here; message loading remains the source of truth.
      });
    }
  }, [loadSessions, sessions.length]);

  useEffect(() => {
    if (sessionId) {
      loadMessages(sessionId).catch((err) => {
        const errorMessage = getApiErrorMessage(err, '加载会话失败');
        if (errorMessage.includes('会话不存在')) {
          message.warning('当前会话不存在，可能因为后端重启已失效，请重新创建对话');
          navigate('/chats', { replace: true });
          return;
        }
        message.error(errorMessage);
      });
    }
  }, [sessionId, loadMessages, message, navigate]);

  useEffect(() => {
    if (error) {
      if (error.includes('会话不存在')) {
        message.warning('当前会话不存在，可能因为后端重启已失效，请重新创建对话');
        navigate('/chats', { replace: true });
        return;
      }
      message.error(error);
    }
  }, [error, message, navigate]);

  const handleSend = async () => {
    const query = inputValue.trim();
    if (!query || !sessionId || isStreaming) return;
    setInputValue('');
    // Clear image attachment after send
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
    }
    setImagePreview(null);
    await sendMessage(sessionId, query);
  };

  const handleImageSelected = useCallback((file: File) => {
    setImagePreview(URL.createObjectURL(file));
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Layout className="chatdetail-layout">
      <Header className="chatdetail-header">
        <div className="chatdetail-header-shell">
          <Button
            className="chatdetail-back"
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/chats')}
          />
          <div className="chatdetail-header-copy">
            <Title level={1} className="display-title">
              古籍知识对话
            </Title>
            <p>围绕证候、方剂、出处和辨证依据组织回答，适合连续追问和引用查看。</p>
            {currentSession?.case_profile_name && (
              <div className="chatdetail-profile-line">
                当前角色：{currentSession.case_profile_name}
                {currentSession.case_profile_summary ? ` · ${currentSession.case_profile_summary}` : ''}
              </div>
            )}
          </div>
        </div>
      </Header>
      <Content className="chatdetail-content">
        <ChatWindow
          messages={messages}
          isStreaming={isStreaming}
          streamContent={streamingContent}
          loading={loading}
        />
      </Content>
      <Footer className="chatdetail-footer">
        <div className="chatdetail-footer-shell">
          {imagePreview && (
            <div className="chatdetail-attachment-strip">
              <Image
                src={imagePreview}
                alt="附件预览"
                width={48}
                height={48}
                style={{ objectFit: 'cover', borderRadius: 12 }}
              />
              <span>图片已加入本轮输入，后续可以扩展为多模态检索和分析。</span>
            </div>
          )}
          <div className="chatdetail-input-row">
            <UploadImagePanel onImageSelected={handleImageSelected} />
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="请输入您的问题，例如：失眠伴口苦烦躁，中医一般怎么辨证？"
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={isStreaming}
              className="chatdetail-textarea"
            />
            {isStreaming ? (
              <Button
                type="default"
                danger
                onClick={cancelStream}
                className="chatdetail-send-btn"
              >
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className="chatdetail-send-btn"
              >
                发送
              </Button>
            )}
          </div>
        </div>
      </Footer>
    </Layout>
  );
};

export default ChatDetail;

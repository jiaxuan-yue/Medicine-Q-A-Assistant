import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Input, Button, Layout, Typography, Image, message } from 'antd';
import { SendOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useChatStore } from '../stores/chatStore';
import { useSSE } from '../hooks/useSSE';
import ChatWindow from '../components/ChatWindow';
import UploadImagePanel from '../components/UploadImagePanel';
import './ChatDetail.css';

const { Header, Content, Footer } = Layout;
const { Title } = Typography;
const { TextArea } = Input;

const ChatDetail: React.FC = () => {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [inputValue, setInputValue] = useState('');
  const [attachedImage, setAttachedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const { messages, loading, loadMessages, isStreaming, streamingContent } =
    useChatStore();
  const { sendMessage, error, cancelStream } = useSSE();

  useEffect(() => {
    if (sessionId) {
      loadMessages(sessionId);
    }
  }, [sessionId, loadMessages]);

  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const handleSend = async () => {
    const query = inputValue.trim();
    if (!query || !sessionId || isStreaming) return;
    setInputValue('');
    // Clear image attachment after send
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
    }
    setAttachedImage(null);
    setImagePreview(null);
    await sendMessage(sessionId, query);
  };

  const handleImageSelected = useCallback((file: File) => {
    setAttachedImage(file);
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
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/chats')}
          style={{ color: '#fff' }}
        />
        <Title level={4} style={{ margin: 0, color: '#fff', flex: 1, textAlign: 'center' }}>
          中医问诊
        </Title>
        <div style={{ width: 32 }} />
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
        {imagePreview && (
          <div style={{ padding: '8px 16px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Image
              src={imagePreview}
              alt="附件预览"
              width={48}
              height={48}
              style={{ objectFit: 'cover', borderRadius: 4 }}
            />
            <span style={{ fontSize: 12, color: '#999' }}>图片已选择</span>
          </div>
        )}
        <div className="chatdetail-input-row">
          <UploadImagePanel onImageSelected={handleImageSelected} />
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="请输入您的问题..."
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
      </Footer>
    </Layout>
  );
};

export default ChatDetail;

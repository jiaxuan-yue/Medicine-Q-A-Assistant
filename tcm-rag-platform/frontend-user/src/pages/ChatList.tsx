import React, { useEffect } from 'react';
import { List, Button, Typography, Layout, Empty } from 'antd';
import { PlusOutlined, MessageOutlined, LogoutOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '../stores/chatStore';
import { useAuthStore } from '../stores/authStore';
import './ChatList.css';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

const ChatList: React.FC = () => {
  const navigate = useNavigate();
  const { sessions, loading, loadSessions, createSession } = useChatStore();
  const { logout } = useAuthStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleNewChat = async () => {
    try {
      const session = await createSession();
      navigate(`/chats/${session.session_id}`);
    } catch {
      // error handled in store
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <Layout className="chatlist-layout">
      <Header className="chatlist-header">
        <div className="chatlist-header-left">
          <span className="chatlist-logo">🏥</span>
          <Title level={4} style={{ margin: 0, color: '#fff' }}>
            中医智能问诊
          </Title>
        </div>
        <Button
          type="text"
          icon={<LogoutOutlined />}
          onClick={handleLogout}
          style={{ color: '#fff' }}
        >
          退出
        </Button>
      </Header>
      <Content className="chatlist-content">
        <div className="chatlist-actions">
          <Button
            type="primary"
            icon={<PlusOutlined />}
            size="large"
            onClick={handleNewChat}
          >
            新建对话
          </Button>
        </div>
        {sessions.length === 0 && !loading ? (
          <Empty description="暂无对话记录，点击上方按钮开始问诊" />
        ) : (
          <List
            loading={loading}
            dataSource={sessions}
            renderItem={(session) => (
              <List.Item
                className="chatlist-item"
                onClick={() => navigate(`/chats/${session.session_id}`)}
              >
                <List.Item.Meta
                  avatar={<MessageOutlined style={{ fontSize: 24, color: '#1677ff' }} />}
                  title={session.title || '新对话'}
                  description={
                    <div>
                      {session.summary && (
                        <Text type="secondary" ellipsis>
                          {session.summary}
                        </Text>
                      )}
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {new Date(session.updated_at).toLocaleString('zh-CN')}
                      </Text>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Content>
    </Layout>
  );
};

export default ChatList;

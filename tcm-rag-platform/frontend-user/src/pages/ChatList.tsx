import React, { useEffect } from 'react';
import { List, Button, Typography, Layout, Empty } from 'antd';
import {
  PlusOutlined,
  LogoutOutlined,
  ArrowRightOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '../stores/chatStore';
import { useAuthStore } from '../stores/authStore';
import { useCaseProfilesStore } from '../stores/caseProfilesStore';
import './ChatList.css';

const { Header, Content } = Layout;
const { Title } = Typography;

const ChatList: React.FC = () => {
  const navigate = useNavigate();
  const { sessions, loading, loadSessions } = useChatStore();
  const { logout } = useAuthStore();
  const { profiles, openManager, openPicker } = useCaseProfilesStore();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleNewChat = async () => {
    openPicker();
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <Layout className="chatlist-layout">
      <Header className="chatlist-header">
        <div className="chatlist-brand">
          <div className="chatlist-brand-mark">岐</div>
          <div className="chatlist-brand-copy">
            <strong>四季有方，三餐有养</strong>
          </div>
        </div>
        <Button
          className="chatlist-logout"
          icon={<LogoutOutlined />}
          onClick={handleLogout}
        >
          退出
        </Button>
      </Header>
      <Content className="chatlist-content">
        <section className="chatlist-hero">
          <div className="chatlist-hero-copy">
            <Title className="display-title" level={1}>
              把问题问得更准
              <br />
              把出处看得更清
            </Title>
            <p>
              想来一碗凉茶or汤？先问问你的体质，最近天气，流传的医书
            </p>
            <div className="chatlist-hero-stats">
              <div className="chatlist-stat">
                <span>最近会话</span>
                <strong>{sessions.length}</strong>
              </div>
              <div className="chatlist-stat">
                <span>中医古籍</span>
                <strong>700+</strong>
              </div>
              <div className="chatlist-stat">
                <span>知识重点</span>
                <strong>膳有古方</strong>
              </div>
              <div className="chatlist-stat">
                <span>望闻问切</span>
                <strong>舌苔与追问</strong>
              </div>
            </div>
            <div className="chatlist-profile-summary">
              <div>
                <span>当前角色库</span>
                <strong>共 {profiles.length} 个角色档案，每次新建对话都需要先选择一个角色进入会话。</strong>
              </div>
              <Button icon={<ProfileOutlined />} onClick={() => openManager()}>
                管理角色档案
              </Button>
            </div>
          </div>
          <div className="chatlist-hero-panel">
            <div className="chatlist-cta-card">
              <h2>开始新的问答</h2>
              <p>适合直接输入症状、方剂名、古籍出处，或把上一轮问题继续追问下去。</p>
              <div className="chatlist-cta-actions">
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  size="large"
                  onClick={handleNewChat}
                >
                  新建对话
                </Button>
              </div>
            </div>
            <div className="chatlist-note-list">
              <button
                type="button"
                className="chatlist-library-entry"
                onClick={() => navigate('/bookshelf')}
              >
                <span>藏书楼入口</span>
                <strong>700+ 册中医古籍一屏总览</strong>
                <p>从《神农本草经》到近现代医案，按类别浏览，点书名即可复制。</p>
                <em>
                  打开书架 <ArrowRightOutlined />
                </em>
              </button>
            </div>
          </div>
        </section>

        <section className="chatlist-section">
          <div className="chatlist-section-header">
            <div className="chatlist-section-title">
              <h2>角色档案</h2>
              <p>一个角色就是一个就诊对象</p>
            </div>
            <span>{profiles.length ? `共 ${profiles.length} 个角色` : '还没有角色档案'}</span>
          </div>
          {profiles.length === 0 ? (
            <Empty
              className="chatlist-empty"
              description="请先创建一个角色档案，再开始新的问答"
            />
          ) : (
            <List
              className="chatlist-session-list"
              dataSource={profiles}
              renderItem={(profile, index) => (
                <List.Item className="chatlist-item">
                  <div className="chatlist-item-card" onClick={() => openManager(profile)}>
                    <div className="chatlist-item-icon">{index + 1}</div>
                    <div className="chatlist-item-main">
                      <strong>{profile.profile_name}</strong>
                      <p>{profile.summary || '补充身高、体重、既往病史、当前用药等基础信息。'}</p>
                    </div>
                    <div className="chatlist-item-meta">
                      <div>{profile.updated_at ? new Date(profile.updated_at).toLocaleString('zh-CN') : '-'}</div>
                      <div style={{ marginTop: 8, color: 'var(--sage)' }}>
                        编辑角色 <ArrowRightOutlined />
                      </div>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          )}
        </section>

        <section className="chatlist-section" style={{ marginTop: 20 }}>
          <div className="chatlist-section-header">
            <h2>最近会话</h2>
            <span>{sessions.length ? `共 ${sessions.length} 条记录` : '还没有会话历史'}</span>
          </div>
          {sessions.length === 0 && !loading ? (
            <Empty
              className="chatlist-empty"
              description="暂无对话记录，点击上方按钮开始第一轮问答"
            />
          ) : (
            <List
              className="chatlist-session-list"
              loading={loading}
              dataSource={sessions}
              renderItem={(session, index) => (
                <List.Item className="chatlist-item">
                  <div
                    className="chatlist-item-card"
                    onClick={() => navigate(`/chats/${session.session_id}`)}
                  >
                    <div className="chatlist-item-icon">{index + 1}</div>
                    <div className="chatlist-item-main">
                      <strong>{session.title || '新对话'}</strong>
                      <p>
                        {(session.case_profile_name ? `角色：${session.case_profile_name} · ` : '') +
                          (session.summary || '继续围绕当前问题补充病机、出处和辨证线索。')}
                      </p>
                    </div>
                    <div className="chatlist-item-meta">
                      <div>{new Date(session.updated_at).toLocaleString('zh-CN')}</div>
                      <div style={{ marginTop: 8, color: 'var(--sage)' }}>
                        继续查看 <ArrowRightOutlined />
                      </div>
                    </div>
                  </div>
                </List.Item>
              )}
            />
          )}
        </section>
      </Content>
    </Layout>
  );
};

export default ChatList;

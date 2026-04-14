import { useState } from 'react';
import { Layout, Menu, Dropdown, Button, Avatar } from 'antd';
import {
  DashboardOutlined,
  UserOutlined,
  FileTextOutlined,
  AuditOutlined,
  ApartmentOutlined,
  SearchOutlined,
  BarChartOutlined,
  BugOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

const { Header, Sider, Content } = Layout;

const menuItems = [
  {
    key: '/admin/dashboard',
    icon: <DashboardOutlined />,
    label: '仪表盘',
  },
  {
    key: '/admin/users',
    icon: <UserOutlined />,
    label: '用户管理',
  },
  {
    key: '/admin/documents',
    icon: <FileTextOutlined />,
    label: '文档管理',
  },
  {
    key: '/admin/documents/review',
    icon: <AuditOutlined />,
    label: '文档审核',
  },
  {
    key: '/admin/graph',
    icon: <ApartmentOutlined />,
    label: '知识图谱',
  },
  {
    key: '/admin/retrieval-logs',
    icon: <SearchOutlined />,
    label: '检索日志',
  },
  {
    key: '/admin/evaluation',
    icon: <BarChartOutlined />,
    label: '评测看板',
  },
  {
    key: '/admin/badcase',
    icon: <BugOutlined />,
    label: 'Badcase分析',
  },
  {
    key: '/admin/model-config',
    icon: <SettingOutlined />,
    label: '模型配置',
  },
];

export default function AdminLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const currentItem =
    menuItems.find((item) => location.pathname.startsWith(String(item.key))) ?? menuItems[0];

  const handleMenuClick = (info: { key: string }) => {
    navigate(info.key);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/admin/login');
  };

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  return (
    <Layout className="admin-app-shell">
      <Sider
        className="admin-sider"
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme="dark"
        width={220}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
        }}
      >
        <div className="admin-sider-inner">
          <div className="admin-sider-brand">
            <div className="admin-sider-mark">岐</div>
            {!collapsed && (
              <div className="admin-sider-brand-copy">
                <span className="admin-sider-eyebrow">TCM Ops Console</span>
                <strong className="admin-sider-title">知识服务管理台</strong>
                <span className="admin-sider-subtitle">RAG · 图谱 · 评测 · 反馈</span>
              </div>
            )}
          </div>
          <div className="admin-sider-divider" />
          <Menu
            className="admin-sider-menu"
            theme="dark"
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={handleMenuClick}
          />
          {!collapsed && (
            <div className="admin-sider-footer">
              当前视图覆盖用户、知识资产、评测和反馈闭环，方便从运营视角统一判断平台状态。
            </div>
          )}
        </div>
      </Sider>
      <Layout className="admin-main" style={{ marginLeft: collapsed ? 80 : 220 }}>
        <Header className="admin-topbar">
          <div className="admin-topbar-left">
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              style={{ fontSize: 16, width: 48, height: 48 }}
            />
            <div className="admin-topbar-copy">
              <span className="admin-topbar-eyebrow">Operations Workspace</span>
              <strong>{String(currentItem.label)}</strong>
            </div>
          </div>
          <div className="admin-topbar-right">
            <div className="admin-topbar-status">知识资产 / 质量闭环 / 平台运营</div>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <div className="admin-user-pill" style={{ cursor: 'pointer' }}>
                <Avatar icon={<UserOutlined />} style={{ background: '#0f5f55' }} />
                <div className="admin-user-copy">
                  <strong>{user?.username ?? '管理员'}</strong>
                  <span>管理端登录</span>
                </div>
              </div>
            </Dropdown>
          </div>
        </Header>
        <div className="admin-content-wrap">
          <Content className="admin-surface admin-content">
            <Outlet />
          </Content>
        </div>
      </Layout>
    </Layout>
  );
}

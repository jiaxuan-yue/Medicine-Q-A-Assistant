import { useEffect } from 'react';
import { Row, Col, Card, Statistic, Spin } from 'antd';
import {
  UserOutlined,
  FileTextOutlined,
  MessageOutlined,
  CommentOutlined,
  ClockCircleOutlined,
  LikeOutlined,
} from '@ant-design/icons';
import { useAdminStore } from '../stores/adminStore';

export default function Dashboard() {
  const { dashboardStats, loading, loadDashboardStats } = useAdminStore();

  useEffect(() => {
    loadDashboardStats();
  }, [loadDashboardStats]);

  if (loading || !dashboardStats) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  const stats = [
    {
      title: '用户总数',
      value: dashboardStats.total_users,
      icon: <UserOutlined style={{ fontSize: 28, color: '#1890ff' }} />,
      color: '#e6f7ff',
    },
    {
      title: '文档总数',
      value: dashboardStats.total_documents,
      icon: <FileTextOutlined style={{ fontSize: 28, color: '#52c41a' }} />,
      color: '#f6ffed',
    },
    {
      title: '会话总数',
      value: dashboardStats.total_sessions,
      icon: <CommentOutlined style={{ fontSize: 28, color: '#722ed1' }} />,
      color: '#f9f0ff',
    },
    {
      title: '消息总数',
      value: dashboardStats.total_messages,
      icon: <MessageOutlined style={{ fontSize: 28, color: '#fa8c16' }} />,
      color: '#fff7e6',
    },
    {
      title: '待审核文档',
      value: dashboardStats.documents_pending_review,
      icon: <ClockCircleOutlined style={{ fontSize: 28, color: '#f5222d' }} />,
      color: '#fff1f0',
    },
    {
      title: '好评率',
      value: (dashboardStats.feedback_positive_rate * 100).toFixed(1),
      suffix: '%',
      icon: <LikeOutlined style={{ fontSize: 28, color: '#13c2c2' }} />,
      color: '#e6fffb',
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>运营概览</h2>
      <Row gutter={[16, 16]}>
        {stats.map((item) => (
          <Col xs={24} sm={12} lg={8} key={item.title}>
            <Card hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div
                  style={{
                    width: 56,
                    height: 56,
                    borderRadius: 12,
                    background: item.color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </div>
                <Statistic
                  title={item.title}
                  value={item.value}
                  suffix={'suffix' in item ? item.suffix : undefined}
                />
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}

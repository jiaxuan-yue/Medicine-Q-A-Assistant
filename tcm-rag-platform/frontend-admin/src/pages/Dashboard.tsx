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
    <div className="admin-page">
      <section className="admin-hero-card">
        <div className="admin-hero-content">
          <div className="admin-hero-copy">
            <div className="section-badge">Overview</div>
            <h2>用一眼可读的方式判断平台规模、健康度和待处理压力。</h2>
            <p>
              这个仪表盘的目标不是堆指标，而是让你快速知道今天该优先补知识资产、处理审核积压，还是回头优化用户问答体验。
            </p>
          </div>
          <div className="admin-hero-metrics">
            <div className="admin-mini-stat">
              <span>用户规模</span>
              <strong>{dashboardStats.total_users}</strong>
            </div>
            <div className="admin-mini-stat">
              <span>文档资产</span>
              <strong>{dashboardStats.total_documents}</strong>
            </div>
            <div className="admin-mini-stat">
              <span>好评率</span>
              <strong>{(dashboardStats.feedback_positive_rate * 100).toFixed(1)}%</strong>
            </div>
          </div>
        </div>
      </section>

      <div className="admin-page-header">
        <div>
          <h1>运营概览</h1>
          <p>从核心指标看平台规模、内容积压和用户满意度，为下一步运营动作提供方向。</p>
        </div>
      </div>

      <Row gutter={[16, 16]}>
        {stats.map((item) => (
          <Col xs={24} sm={12} lg={8} key={item.title}>
            <Card hoverable className="admin-stat-card">
              <div className="admin-stat-shell">
                <div className="admin-stat-icon" style={{ background: item.color }}>
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

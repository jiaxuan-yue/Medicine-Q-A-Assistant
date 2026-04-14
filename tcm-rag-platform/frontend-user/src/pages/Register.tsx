import React from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import './Login.css'; // reuse login styles

const { Title, Text } = Typography;

const Register: React.FC = () => {
  const navigate = useNavigate();
  const { register, loading } = useAuthStore();

  const onFinish = async (values: {
    username: string;
    email: string;
    password: string;
  }) => {
    try {
      await register({
        username: values.username,
        email: values.email,
        password: values.password,
      });
      message.success('注册成功');
      navigate('/chats');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { message?: string } } };
      message.error(error.response?.data?.message || '注册失败，请稍后重试');
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <section className="auth-brand-panel">
          <div className="auth-brand-inner">
            <div className="auth-brand-header">
              <div className="auth-brand-mark">典</div>
              <div className="auth-brand-title">
                <span>Build Your Workspace</span>
                <strong>进入可信的中医知识协作界面</strong>
              </div>
            </div>
            <div className="section-badge">Create Access</div>
            <Title className="auth-heading display-title" level={1}>
              注册之后，你可以把提问、出处、反馈和评测放到同一个闭环里。
            </Title>
            <p className="auth-description">
              这不是普通聊天页，而是面向知识服务的工作台。每次提问都会更接近规范术语、结构化检索和可解释回答。
            </p>
            <div className="auth-stat-grid">
              <div className="auth-stat-card">
                <span>问答模式</span>
                <strong>多轮会话</strong>
              </div>
              <div className="auth-stat-card">
                <span>引用风格</span>
                <strong>可追溯</strong>
              </div>
              <div className="auth-stat-card">
                <span>优化方式</span>
                <strong>反馈驱动</strong>
              </div>
            </div>
            <ul className="auth-feature-list">
              <li className="auth-feature-item">
                <div className="auth-feature-index">01</div>
                <div className="auth-feature-copy">
                  <strong>适合检索复杂中医问题</strong>
                  <span>围绕证候、方剂、出处和辨证依据组织问题，而不是只看表层症状。</span>
                </div>
              </li>
              <li className="auth-feature-item">
                <div className="auth-feature-index">02</div>
                <div className="auth-feature-copy">
                  <strong>保留后续扩展空间</strong>
                  <span>注册后即可体验用户端问答，后续也能衔接后台运营和评测能力。</span>
                </div>
              </li>
            </ul>
          </div>
        </section>

        <Card className="auth-card" bordered={false}>
          <div className="auth-form-copy">
            <div className="section-badge">Register</div>
            <Title level={2}>创建账号</Title>
            <Text>加入中医药智能知识服务平台，开始你的第一轮会话。</Text>
          </div>
          <Form
            name="register"
            onFinish={onFinish}
            size="large"
            autoComplete="off"
            className="auth-form"
          >
            <Form.Item
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 3, message: '用户名至少3个字符' },
              ]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item
              name="email"
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '请输入有效的邮箱地址' },
              ]}
            >
              <Input prefix={<MailOutlined />} placeholder="邮箱" />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 6, message: '密码至少6个字符' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次密码输入不一致'));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                注册并进入
              </Button>
            </Form.Item>
            <div className="auth-footer">
              <Text>已有账号？</Text>
              <Link to="/login">立即登录</Link>
            </div>
          </Form>
        </Card>
      </div>
    </div>
  );
};

export default Register;

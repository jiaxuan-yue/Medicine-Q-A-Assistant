import React from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import type { LoginRequest } from '../types';
import './Login.css';

const { Title, Text } = Typography;

function getErrorMessage(err: unknown): string {
  const error = err as {
    response?: {
      data?: {
        message?: string;
      };
    };
  };
  return error.response?.data?.message || '登录失败，请检查用户名和密码';
}

const Login: React.FC = () => {
  const navigate = useNavigate();
  const { login, loading } = useAuthStore();
  const [form] = Form.useForm<LoginRequest>();

  const onFinish = async (values: LoginRequest) => {
    form.setFields([
      { name: 'username', errors: [] },
      { name: 'password', errors: [] },
    ]);

    try {
      await login(values);
      message.success('登录成功');
      navigate('/chats');
    } catch (err: unknown) {
      const errorMessage = getErrorMessage(err);
      form.setFields([
        { name: 'password', errors: [errorMessage] },
      ]);
      message.error(errorMessage);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-shell">
        <section className="auth-brand-panel">
          <div className="auth-brand-inner">
            <div className="auth-brand-header">
              <div className="auth-brand-mark">岐</div>
              <div className="auth-brand-title">
                <span>TCM Knowledge Service</span>
                <strong>中医药智能知识服务平台</strong>
              </div>
            </div>
            <div className="section-badge">Ancient Texts · RAG · Citations</div>
            <Title className="auth-heading display-title" level={1}>
              把古籍里的辨证线索，整理成更可信、更可追溯的对话体验。
            </Title>
            <p className="auth-description">
              面向中医知识问答场景，围绕症状、证候、方剂与出处组织回答。所有回答都尽量回到文献依据，而不是停留在泛泛生成。
            </p>
            <div className="auth-stat-grid">
              <div className="auth-stat-card">
                <span>流式输出</span>
                <strong>SSE</strong>
              </div>
              <div className="auth-stat-card">
                <span>知识来源</span>
                <strong>古籍 / 图谱</strong>
              </div>
              <div className="auth-stat-card">
                <span>核心目标</span>
                <strong>可信问答</strong>
              </div>
            </div>
            <ul className="auth-feature-list">
              <li className="auth-feature-item">
                <div className="auth-feature-index">01</div>
                <div className="auth-feature-copy">
                  <strong>检索优先，不直接拍脑袋回答</strong>
                  <span>把问答组织成“问题理解、证候线索、引用出处”的完整路径。</span>
                </div>
              </li>
              <li className="auth-feature-item">
                <div className="auth-feature-index">02</div>
                <div className="auth-feature-copy">
                  <strong>支持反馈闭环</strong>
                  <span>用户反馈、badcase 和评测数据会继续反哺检索与生成质量。</span>
                </div>
              </li>
            </ul>
          </div>
        </section>

        <Card className="auth-card" bordered={false}>
          <div className="auth-form-copy">
            <div className="section-badge">Sign In</div>
            <Title level={2}>登录平台</Title>
            <Text>进入中医知识问答与管理工作流，继续你的会话和检索记录。</Text>
          </div>
          <Form
            form={form}
            name="login"
            onFinish={onFinish}
            onValuesChange={() => {
              form.setFields([
                { name: 'username', errors: [] },
                { name: 'password', errors: [] },
              ]);
            }}
            size="large"
            autoComplete="off"
            className="auth-form"
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录并继续
              </Button>
            </Form.Item>
            <div className="auth-footer">
              <Text>还没有账号？</Text>
              <Link to="/register">立即注册</Link>
            </div>
          </Form>
        </Card>
      </div>
    </div>
  );
};

export default Login;

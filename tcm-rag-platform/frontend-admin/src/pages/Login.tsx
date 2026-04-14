import { useState } from 'react';
import { Form, Input, Button, Card, App } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';

function getErrorMessage(error: unknown): string {
  const err = error as {
    response?: {
      data?: {
        message?: string;
      };
    };
  };
  return err.response?.data?.message || '登录失败，请检查用户名和密码';
}

export default function Login() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const { message } = App.useApp();
  const [form] = Form.useForm<{ username: string; password: string }>();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    form.setFields([
      { name: 'username', errors: [] },
      { name: 'password', errors: [] },
    ]);
    try {
      await login(values.username, values.password);
      message.success('登录成功');
      navigate('/admin/dashboard');
    } catch (error) {
      const errorMessage = getErrorMessage(error);
      form.setFields([{ name: 'password', errors: [errorMessage] }]);
      message.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="admin-login-page">
      <div className="admin-login-shell">
        <section className="admin-login-brand">
          <div className="section-badge">Operations · Quality · Knowledge</div>
          <h1>让文档、评测、反馈与平台运营在同一个工作台里协同运转。</h1>
          <p>
            这是中医药知识服务平台的管理入口。你可以从这里掌握知识资产状态、问答质量变化和用户反馈趋势，把平台从“可用”继续打磨到“可靠”。
          </p>
          <div className="admin-login-notes">
            <div className="admin-login-note">
              文档上传、审核与发布状态集中查看，适合快速追踪知识库建设进度。
            </div>
            <div className="admin-login-note">
              评测与 badcase 反馈结合，方便把模型效果问题沉淀成后续优化任务。
            </div>
          </div>
        </section>

        <Card className="admin-login-card">
          <div className="admin-login-copy">
            <div className="section-badge">Admin Login</div>
            <h2>登录管理端</h2>
            <p>使用管理员或运营账号进入控制台，继续处理平台运营与知识治理工作。</p>
          </div>
          <Form
            form={form}
            name="admin_login"
            onFinish={onFinish}
            onValuesChange={() => {
              form.setFields([
                { name: 'username', errors: [] },
                { name: 'password', errors: [] },
              ]);
            }}
            size="large"
            autoComplete="off"
          >
            <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
              <Input prefix={<UserOutlined />} placeholder="用户名" />
            </Form.Item>
            <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="密码" />
            </Form.Item>
            <Form.Item style={{ marginTop: 28, marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" loading={loading} block>
                登录并进入控制台
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    </div>
  );
}

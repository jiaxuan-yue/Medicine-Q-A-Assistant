import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AdminLayout from './components/AdminLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import UserManagement from './pages/UserManagement';
import DocumentManagement from './pages/DocumentManagement';
import DocumentReview from './pages/DocumentReview';
import GraphManagement from './pages/GraphManagement';
import EvalDashboardPage from './pages/EvalDashboard';
import RetrievalLogs from './pages/RetrievalLogs';
import BadcaseDashboard from './pages/BadcaseDashboard';
import ModelConfig from './pages/ModelConfig';
import { useAuthStore } from './stores/authStore';
import type { ReactNode } from 'react';

function AuthGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/admin/login" replace />;
  }
  return <>{children}</>;
}

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#0f5f55',
          colorInfo: '#0f5f55',
          colorSuccess: '#0f5f55',
          colorWarning: '#c48c4b',
          colorError: '#b15746',
          colorTextBase: '#102b27',
          colorBgLayout: 'transparent',
          colorBgContainer: '#f8fbf9',
          colorBorder: 'rgba(16, 43, 39, 0.12)',
          fontFamily: "'Noto Sans SC', sans-serif",
          borderRadius: 18,
          borderRadiusLG: 24,
          boxShadowSecondary: '0 18px 48px rgba(12, 41, 36, 0.1)',
        },
        components: {
          Layout: {
            headerBg: 'transparent',
            bodyBg: 'transparent',
            siderBg: 'transparent',
          },
          Menu: {
            darkItemBg: 'transparent',
            darkItemSelectedBg: 'rgba(255, 255, 255, 0.12)',
            darkItemHoverBg: 'rgba(255, 255, 255, 0.08)',
            darkSubMenuItemBg: 'transparent',
            itemBorderRadius: 14,
          },
          Button: {
            colorPrimary: '#0f5f55',
            colorPrimaryHover: '#0a4e46',
            colorPrimaryActive: '#083f39',
            primaryShadow: 'none',
            controlHeight: 42,
            fontWeight: 600,
          },
          Card: {
            borderRadiusLG: 24,
          },
          Table: {
            headerBg: 'rgba(15, 95, 85, 0.04)',
            headerSplitColor: 'rgba(16, 43, 39, 0.08)',
            rowHoverBg: 'rgba(15, 95, 85, 0.04)',
          },
          Tabs: {
            inkBarColor: '#c48c4b',
            itemColor: '#5f7772',
            itemSelectedColor: '#102b27',
            itemHoverColor: '#0f5f55',
          },
          Input: {
            activeBorderColor: '#0f5f55',
            hoverBorderColor: '#0f5f55',
          },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Routes>
            <Route path="/admin/login" element={<Login />} />
            <Route
              path="/admin"
              element={
                <AuthGuard>
                  <AdminLayout />
                </AuthGuard>
              }
            >
              <Route index element={<Navigate to="/admin/dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="users" element={<UserManagement />} />
              <Route path="documents" element={<DocumentManagement />} />
              <Route path="documents/review" element={<DocumentReview />} />
              <Route path="graph" element={<GraphManagement />} />
              <Route path="evaluation" element={<EvalDashboardPage />} />
              <Route path="retrieval-logs" element={<RetrievalLogs />} />
              <Route path="badcase" element={<BadcaseDashboard />} />
              <Route path="model-config" element={<ModelConfig />} />
            </Route>
            <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  );
}

export default App;

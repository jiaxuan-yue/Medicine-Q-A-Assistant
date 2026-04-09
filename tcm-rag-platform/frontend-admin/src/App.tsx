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
    <ConfigProvider locale={zhCN}>
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

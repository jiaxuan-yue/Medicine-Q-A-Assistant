import React, { useEffect } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
} from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useAuthStore } from './stores/authStore';
import Login from './pages/Login';
import Register from './pages/Register';
import ChatList from './pages/ChatList';
import ChatDetail from './pages/ChatDetail';
import CaseProfilesGuard from './components/CaseProfilesGuard';

// Route guard component
const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

// Redirect if already authenticated
const GuestOnly: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();

  if (isAuthenticated) {
    return <Navigate to="/chats" replace />;
  }

  return <>{children}</>;
};

// Hydrate auth state on mount
const AuthHydrator: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return <>{children}</>;
};

const App: React.FC = () => {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#285d4c',
          colorInfo: '#285d4c',
          colorSuccess: '#285d4c',
          colorWarning: '#c69654',
          colorError: '#b8593d',
          colorTextBase: '#1e342d',
          colorBgBase: '#fbf8f1',
          colorBorder: 'rgba(30, 52, 45, 0.12)',
          fontFamily: "'Noto Sans SC', sans-serif",
          borderRadius: 18,
          borderRadiusLG: 24,
          boxShadowSecondary: '0 18px 48px rgba(28, 43, 38, 0.12)',
        },
        components: {
          Layout: {
            bodyBg: 'transparent',
            headerBg: 'transparent',
            footerBg: 'transparent',
          },
          Button: {
            controlHeight: 44,
            colorPrimary: '#285d4c',
            colorPrimaryHover: '#1f5140',
            colorPrimaryActive: '#17392f',
            primaryShadow: 'none',
            fontWeight: 600,
          },
          Input: {
            activeBorderColor: '#285d4c',
            hoverBorderColor: '#285d4c',
          },
          Card: {
            borderRadiusLG: 28,
          },
          Collapse: {
            headerBg: 'rgba(40, 93, 76, 0.04)',
            contentBg: 'rgba(255, 253, 248, 0.8)',
          },
        },
      }}
    >
      <BrowserRouter>
        <AuthHydrator>
          <Routes>
            <Route path="/" element={<Navigate to="/chats" replace />} />
            <Route
              path="/login"
              element={
                <GuestOnly>
                  <Login />
                </GuestOnly>
              }
            />
            <Route
              path="/register"
              element={
                <GuestOnly>
                  <Register />
                </GuestOnly>
              }
            />
            <Route
              path="/chats"
              element={
                <RequireAuth>
                  <CaseProfilesGuard>
                    <ChatList />
                  </CaseProfilesGuard>
                </RequireAuth>
              }
            />
            <Route
              path="/chats/:sessionId"
              element={
                <RequireAuth>
                  <CaseProfilesGuard>
                    <ChatDetail />
                  </CaseProfilesGuard>
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/chats" replace />} />
          </Routes>
        </AuthHydrator>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;

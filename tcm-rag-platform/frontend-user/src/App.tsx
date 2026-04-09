import React, { useEffect } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useAuthStore } from './stores/authStore';
import Login from './pages/Login';
import Register from './pages/Register';
import ChatList from './pages/ChatList';
import ChatDetail from './pages/ChatDetail';

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
    <ConfigProvider locale={zhCN}>
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
                  <ChatList />
                </RequireAuth>
              }
            />
            <Route
              path="/chats/:sessionId"
              element={
                <RequireAuth>
                  <ChatDetail />
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

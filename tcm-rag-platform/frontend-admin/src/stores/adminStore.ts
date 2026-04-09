import { create } from 'zustand';
import type { User, Document, DashboardStats } from '../types';
import { userApi } from '../api/user';
import { documentApi } from '../api/document';
import { adminApi } from '../api/admin';
import { message } from 'antd';

interface AdminState {
  users: User[];
  usersTotal: number;
  documents: Document[];
  documentsTotal: number;
  dashboardStats: DashboardStats | null;
  loading: boolean;

  loadUsers: (params?: { page?: number; size?: number; role?: string }) => Promise<void>;
  loadDocuments: (params?: { page?: number; size?: number; status?: string }) => Promise<void>;
  loadDashboardStats: () => Promise<void>;
  uploadDocument: (formData: FormData) => Promise<void>;
  updateUserRole: (userId: number, role: string) => Promise<void>;
}

export const useAdminStore = create<AdminState>((set) => ({
  users: [],
  usersTotal: 0,
  documents: [],
  documentsTotal: 0,
  dashboardStats: null,
  loading: false,

  loadUsers: async (params) => {
    set({ loading: true });
    try {
      const { data } = await userApi.list(params ?? {});
      set({
        users: data.data.items,
        usersTotal: data.data.total,
        loading: false,
      });
    } catch {
      set({ loading: false });
      message.error('加载用户列表失败');
    }
  },

  loadDocuments: async (params) => {
    set({ loading: true });
    try {
      const { data } = await documentApi.list(params ?? {});
      set({
        documents: data.data.items,
        documentsTotal: data.data.total,
        loading: false,
      });
    } catch {
      set({ loading: false });
      message.error('加载文档列表失败');
    }
  },

  loadDashboardStats: async () => {
    set({ loading: true });
    try {
      const { data } = await adminApi.getDashboardStats();
      set({ dashboardStats: data.data, loading: false });
    } catch {
      set({ loading: false });
      message.error('加载仪表盘数据失败');
    }
  },

  uploadDocument: async (formData: FormData) => {
    set({ loading: true });
    try {
      await documentApi.upload(formData);
      message.success('文档上传成功');
      set({ loading: false });
    } catch {
      set({ loading: false });
      message.error('文档上传失败');
    }
  },

  updateUserRole: async (userId: number, role: string) => {
    try {
      await userApi.updateRole(userId, role);
      message.success('角色更新成功');
    } catch {
      message.error('角色更新失败');
    }
  },
}));

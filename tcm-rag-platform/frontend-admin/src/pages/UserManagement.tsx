import { useEffect, useState, useCallback } from 'react';
import { Table, Select, Input, Space, App } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { User } from '../types';
import { useAdminStore } from '../stores/adminStore';
import { formatDate } from '../utils';

const roleOptions = [
  { label: '管理员', value: 'admin' },
  { label: '审核员', value: 'reviewer' },
  { label: '运营', value: 'operator' },
  { label: '用户', value: 'user' },
];

export default function UserManagement() {
  const { users, usersTotal, loading, loadUsers, updateUserRole } = useAdminStore();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [search, setSearch] = useState('');
  const { message } = App.useApp();

  const fetchUsers = useCallback(() => {
    loadUsers({ page, size: pageSize, role: roleFilter });
  }, [loadUsers, page, pageSize, roleFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleRoleChange = async (userId: number, role: string) => {
    await updateUserRole(userId, role);
    fetchUsers();
    message.success('角色已更新');
  };

  const filteredUsers = search
    ? users.filter(
        (u) =>
          u.username.toLowerCase().includes(search.toLowerCase()) ||
          u.email.toLowerCase().includes(search.toLowerCase())
      )
    : users;

  const columns: ColumnsType<User> = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      width: 140,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 200,
      ellipsis: true,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 140,
      render: (role: string, record) => (
        <Select
          value={role}
          options={roleOptions}
          onChange={(val) => handleRoleChange(record.id, val)}
          style={{ width: 120 }}
          size="small"
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => formatDate(val),
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>用户管理</h2>
      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="搜索用户名或邮箱"
          allowClear
          onSearch={setSearch}
          onChange={(e) => !e.target.value && setSearch('')}
          style={{ width: 240 }}
        />
        <Select
          placeholder="角色筛选"
          allowClear
          options={roleOptions}
          onChange={setRoleFilter}
          style={{ width: 140 }}
        />
      </Space>
      <Table<User>
        rowKey="id"
        columns={columns}
        dataSource={filteredUsers}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total: usersTotal,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
        scroll={{ x: 800 }}
        size="middle"
      />
    </div>
  );
}

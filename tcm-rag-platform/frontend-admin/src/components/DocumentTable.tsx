import { Table, Tag } from 'antd';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import type { Document } from '../types';
import { formatDate } from '../utils';

const statusColorMap: Record<Document['status'], string> = {
  pending: 'orange',
  processing: 'blue',
  published: 'green',
  rejected: 'red',
  failed: 'red',
};

const statusLabelMap: Record<Document['status'], string> = {
  pending: '待处理',
  processing: '处理中',
  published: '已发布',
  rejected: '已拒绝',
  failed: '失败',
};

interface DocumentTableProps {
  documents: Document[];
  total: number;
  loading: boolean;
  page: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  onAction?: (action: string, doc: Document) => void;
}

export default function DocumentTable({
  documents,
  total,
  loading,
  page,
  pageSize,
  onPageChange,
  onAction,
}: DocumentTableProps) {
  const columns: ColumnsType<Document> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      width: 200,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      width: 120,
      ellipsis: true,
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 70,
      align: 'center',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: Document['status']) => (
        <Tag color={statusColorMap[status]}>{statusLabelMap[status]}</Tag>
      ),
    },
    {
      title: '权威分数',
      dataIndex: 'authority_score',
      key: 'authority_score',
      width: 100,
      align: 'center',
      sorter: (a, b) => a.authority_score - b.authority_score,
      render: (score: number) => score.toFixed(2),
    },
    {
      title: '上传者',
      dataIndex: 'uploaded_by',
      key: 'uploaded_by',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (val: string) => formatDate(val),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_, record) => (
        <span>
          <button type="button" className="admin-table-link" onClick={() => onAction?.('view', record)}>
            查看
          </button>
          <button type="button" className="admin-table-link" onClick={() => onAction?.('reindex', record)}>
            重索引
          </button>
        </span>
      ),
    },
  ];

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showQuickJumper: true,
    showTotal: (t) => `共 ${t} 条`,
    onChange: onPageChange,
  };

  return (
    <Table<Document>
      rowKey="doc_id"
      columns={columns}
      dataSource={documents}
      loading={loading}
      pagination={pagination}
      scroll={{ x: 1000 }}
      size="middle"
    />
  );
}

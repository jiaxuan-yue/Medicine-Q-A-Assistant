import { useEffect, useState, useCallback } from 'react';
import { Tabs, Button, Upload, App } from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { UploadProps } from 'antd';
import DocumentTable from '../components/DocumentTable';
import { useAdminStore } from '../stores/adminStore';
import type { Document } from '../types';

const statusTabs = [
  { key: '', label: '全部' },
  { key: 'pending', label: '待处理' },
  { key: 'processing', label: '处理中' },
  { key: 'published', label: '已发布' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'failed', label: '失败' },
];

export default function DocumentManagement() {
  const { documents, documentsTotal, loading, loadDocuments, uploadDocument } = useAdminStore();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState('');
  const { message } = App.useApp();

  const fetchDocuments = useCallback(() => {
    loadDocuments({
      page,
      size: pageSize,
      status: statusFilter || undefined,
    });
  }, [loadDocuments, page, pageSize, statusFilter]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleTabChange = (key: string) => {
    setStatusFilter(key);
    setPage(1);
  };

  const handlePageChange = (p: number, ps: number) => {
    setPage(p);
    setPageSize(ps);
  };

  const handleAction = (_action: string, _doc: Document) => {
    message.info('功能开发中');
  };

  const uploadProps: UploadProps = {
    accept: '.pdf,.doc,.docx,.txt',
    showUploadList: false,
    beforeUpload: async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      await uploadDocument(formData);
      fetchDocuments();
      return false;
    },
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>文档管理</h2>
        <Upload {...uploadProps}>
          <Button type="primary" icon={<UploadOutlined />}>
            上传文档
          </Button>
        </Upload>
      </div>
      <Tabs
        activeKey={statusFilter}
        onChange={handleTabChange}
        items={statusTabs}
        style={{ marginBottom: 16 }}
      />
      <DocumentTable
        documents={documents}
        total={documentsTotal}
        loading={loading}
        page={page}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        onAction={handleAction}
      />
    </div>
  );
}

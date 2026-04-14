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
    <div className="admin-page">
      <div className="admin-page-header">
        <div>
          <h1>文档管理</h1>
          <p>集中管理上传、状态流转和入库节奏，让知识资产增长与审核节奏保持可控。</p>
        </div>
        <div className="admin-header-actions">
          <Upload {...uploadProps}>
            <Button type="primary" icon={<UploadOutlined />}>
              上传文档
            </Button>
          </Upload>
        </div>
      </div>

      <div className="admin-inline-metrics">
        <div className="admin-inline-metric">
          <span>当前文档数</span>
          <strong>{documentsTotal}</strong>
        </div>
        <div className="admin-inline-metric">
          <span>筛选状态</span>
          <strong>{statusTabs.find((item) => item.key === statusFilter)?.label ?? '全部'}</strong>
        </div>
        <div className="admin-inline-metric">
          <span>运营目标</span>
          <strong>稳定入库 / 清晰审核</strong>
        </div>
      </div>

      <div className="admin-table-card">
        <div className="admin-toolbar">
          <div className="admin-toolbar-left">
            <div className="section-badge">Document Queue</div>
          </div>
          <div className="admin-toolbar-right">支持异步入库、索引构建与状态追踪</div>
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
    </div>
  );
}

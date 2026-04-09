import { useEffect, useState, useCallback } from 'react';
import {
  Table, Select, Tag, Modal, Card, Statistic, Row, Col, Space, Spin, App, Empty, DatePicker,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { feedbackApi } from '../api/feedback';
import type { FeedbackItem, FeedbackStats } from '../types';
import { formatDate } from '../utils';

const { RangePicker } = DatePicker;

const categoryOptions = [
  { label: '改写错误', value: 'rewrite_error' },
  { label: '检索缺失', value: 'retrieval_miss' },
  { label: '重排错误', value: 'rerank_error' },
  { label: '幻觉', value: 'hallucination' },
  { label: '安全缺失', value: 'safety_missing' },
  { label: '其他', value: 'other' },
];

const categoryColorMap: Record<string, string> = {
  rewrite_error: 'orange',
  retrieval_miss: 'red',
  rerank_error: 'volcano',
  hallucination: 'purple',
  safety_missing: 'magenta',
  other: 'default',
};

export default function BadcaseDashboard() {
  const [feedbackList, setFeedbackList] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [selectedItem, setSelectedItem] = useState<FeedbackItem | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const { message } = App.useApp();

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await feedbackApi.list({ page, size: pageSize });
      let items = data.data.items;
      // Client-side filter by category and date since API may not support these filters
      if (categoryFilter) {
        items = items.filter((item) => item.category === categoryFilter);
      }
      if (dateRange) {
        const [start, end] = dateRange;
        items = items.filter((item) => {
          const d = item.created_at;
          return d >= start && d <= end;
        });
      }
      setFeedbackList(items);
      setTotal(data.data.total);
    } catch {
      message.error('加载反馈列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, categoryFilter, dateRange, message]);

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await feedbackApi.getStats();
      setStats(data.data);
    } catch {
      // silently fail
    }
  }, []);

  useEffect(() => {
    fetchList();
    fetchStats();
  }, [fetchList, fetchStats]);

  const handleViewDetail = async (item: FeedbackItem) => {
    setDetailModalOpen(true);
    try {
      const { data } = await feedbackApi.getDetail(item.id);
      setSelectedItem(data.data);
    } catch {
      setSelectedItem(item);
    }
  };

  const columns: ColumnsType<FeedbackItem> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '查询',
      dataIndex: 'query',
      key: 'query',
      width: 200,
      ellipsis: true,
    },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 120,
      render: (category?: string) =>
        category ? (
          <Tag color={categoryColorMap[category] || 'default'}>{category}</Tag>
        ) : (
          '-'
        ),
    },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (val: string) => formatDate(val),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_, record) => (
        <a onClick={() => handleViewDetail(record)}>详情</a>
      ),
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>Badcase 分析</h2>

      {/* Stats cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card hoverable>
            <Statistic title="反馈总数" value={stats?.total ?? '-'} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable>
            <Statistic title="负面反馈" value={stats?.negative ?? '-'} valueStyle={{ color: '#f5222d' }} />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable>
            <Statistic title="正面反馈" value={stats?.positive ?? '-'} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        {stats?.by_category && Object.entries(stats.by_category).map(([cat, count]) => (
          <Col xs={12} sm={6} key={cat}>
            <Card size="small">
              <Statistic
                title={<Tag color={categoryColorMap[cat] || 'default'}>{cat}</Tag>}
                value={count}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filters */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          placeholder="分类筛选"
          allowClear
          options={categoryOptions}
          onChange={setCategoryFilter}
          style={{ width: 160 }}
        />
        <RangePicker
          onChange={(_, dateStrings) => {
            if (dateStrings[0] && dateStrings[1]) {
              setDateRange(dateStrings as [string, string]);
            } else {
              setDateRange(null);
            }
          }}
        />
      </Space>

      <Table<FeedbackItem>
        rowKey="id"
        columns={columns}
        dataSource={feedbackList}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
        scroll={{ x: 700 }}
        size="middle"
      />

      {/* Detail Modal */}
      <Modal
        title="反馈详情"
        open={detailModalOpen}
        onCancel={() => { setDetailModalOpen(false); setSelectedItem(null); }}
        footer={null}
        width={600}
      >
        {selectedItem ? (
          <div>
            <Card size="small" style={{ marginBottom: 12 }}>
              <p><strong>查询：</strong>{selectedItem.query}</p>
            </Card>
            <Card size="small" style={{ marginBottom: 12 }}>
              <p><strong>回答：</strong></p>
              <p style={{ whiteSpace: 'pre-wrap' }}>{selectedItem.answer}</p>
            </Card>
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="评分" value={selectedItem.rating} />
              </Col>
              <Col span={8}>
                <p><strong>分类：</strong></p>
                {selectedItem.category ? (
                  <Tag color={categoryColorMap[selectedItem.category] || 'default'}>{selectedItem.category}</Tag>
                ) : '-'}
              </Col>
              <Col span={8}>
                <Statistic title="时间" value={formatDate(selectedItem.created_at)} valueStyle={{ fontSize: 14 }} />
              </Col>
            </Row>
            {selectedItem.content && (
              <Card size="small" style={{ marginTop: 12 }}>
                <p><strong>反馈内容：</strong></p>
                <p>{selectedItem.content}</p>
              </Card>
            )}
          </div>
        ) : (
          <Spin />
        )}
      </Modal>
    </div>
  );
}

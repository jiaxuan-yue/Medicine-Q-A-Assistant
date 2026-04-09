import { useEffect, useState, useCallback } from 'react';
import {
  Table, Button, Drawer, Statistic, Card, Row, Col, Badge, Select, Space,
  Spin, App, Empty, Divider, Dropdown,
} from 'antd';
import { PlayCircleOutlined, BarChartOutlined, SwapOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { MenuProps } from 'antd';
import { evaluationApi } from '../api/evaluation';
import type { EvalTask, EvalMetrics, EvalComparison } from '../types';
import { formatDate } from '../utils';

const evalTypeOptions = [
  { label: '检索评测', value: 'retrieval' },
  { label: '生成评测', value: 'generation' },
  { label: '改写评测', value: 'rewrite' },
  { label: '全量评测', value: 'full' },
];

const statusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
};

const statusTextMap: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

function MetricsCards({ metrics }: { metrics?: EvalMetrics }) {
  if (!metrics) return <Empty description="暂无指标数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  return (
    <Row gutter={[16, 16]}>
      {metrics.recall_at_5 !== undefined && (
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Recall@5" value={metrics.recall_at_5} precision={4} />
          </Card>
        </Col>
      )}
      {metrics.recall_at_10 !== undefined && (
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Recall@10" value={metrics.recall_at_10} precision={4} />
          </Card>
        </Col>
      )}
      {metrics.mrr !== undefined && (
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="MRR" value={metrics.mrr} precision={4} />
          </Card>
        </Col>
      )}
      {metrics.ndcg !== undefined && (
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="NDCG" value={metrics.ndcg} precision={4} />
          </Card>
        </Col>
      )}
      {Object.entries(metrics)
        .filter(([k]) => !['recall_at_5', 'recall_at_10', 'mrr', 'ndcg'].includes(k))
        .map(([key, val]) =>
          val !== undefined ? (
            <Col xs={12} sm={6} key={key}>
              <Card size="small">
                <Statistic title={key} value={val} precision={4} />
              </Card>
            </Col>
          ) : null
        )}
    </Row>
  );
}

export default function EvalDashboardPage() {
  const [tasks, setTasks] = useState<EvalTask[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedTask, setSelectedTask] = useState<EvalTask | null>(null);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<EvalComparison | null>(null);
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const { message } = App.useApp();

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await evaluationApi.listTasks({ page, size: pageSize });
      setTasks(data.data.items);
      setTotal(data.data.total);
    } catch {
      message.error('加载评测任务失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, message]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const handleRunEval = async (evalType: string) => {
    setRunLoading(true);
    try {
      await evaluationApi.runEval(evalType);
      message.success('评测任务已提交');
      fetchTasks();
    } catch {
      message.error('提交评测任务失败');
    } finally {
      setRunLoading(false);
    }
  };

  const handleViewDetail = async (task: EvalTask) => {
    setDetailDrawerOpen(true);
    setDetailLoading(true);
    try {
      const { data } = await evaluationApi.getTaskDetail(task.id);
      setSelectedTask(data.data);
    } catch {
      message.error('加载任务详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCompare = async () => {
    if (compareIds.length !== 2) {
      message.warning('请选择两个任务进行对比');
      return;
    }
    setCompareDrawerOpen(true);
    setCompareLoading(true);
    try {
      const { data } = await evaluationApi.compareTasks(compareIds[0], compareIds[1]);
      setComparison(data.data);
    } catch {
      message.error('加载对比数据失败');
    } finally {
      setCompareLoading(false);
    }
  };

  const runMenuItems: MenuProps['items'] = evalTypeOptions.map((opt) => ({
    key: opt.value,
    label: opt.label,
    onClick: () => handleRunEval(opt.value),
  }));

  const columns: ColumnsType<EvalTask> = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      ellipsis: true,
    },
    {
      title: '类型',
      dataIndex: 'eval_type',
      key: 'eval_type',
      width: 100,
      render: (type: string) => {
        const opt = evalTypeOptions.find((o) => o.value === type);
        return opt?.label || type;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Badge status={statusColorMap[status] as 'default' | 'processing' | 'success' | 'error'} text={statusTextMap[status] || status} />
      ),
    },
    {
      title: '指标概要',
      key: 'metrics_summary',
      width: 200,
      render: (_, record) => {
        if (!record.metrics) return '-';
        const entries = Object.entries(record.metrics).filter(([, v]) => v !== undefined).slice(0, 3);
        return entries.map(([k, v]) => `${k}: ${Number(v).toFixed(3)}`).join(' | ') || '-';
      },
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
      width: 100,
      render: (_, record) => (
        <Button type="link" size="small" icon={<BarChartOutlined />} onClick={() => handleViewDetail(record)}>
          详情
        </Button>
      ),
    },
  ];

  const completedTasks = tasks.filter((t) => t.status === 'completed');

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>评测看板</h2>
        <Space>
          <Dropdown menu={{ items: runMenuItems }} placement="bottomRight">
            <Button type="primary" icon={<PlayCircleOutlined />} loading={runLoading}>
              运行评测
            </Button>
          </Dropdown>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>对比评测：</span>
          <Select
            mode="multiple"
            placeholder="选择两个已完成任务对比"
            value={compareIds}
            onChange={(vals) => setCompareIds(vals.slice(-2))}
            options={completedTasks.map((t) => ({ label: `${t.id.slice(0, 8)} (${t.eval_type})`, value: t.id }))}
            style={{ minWidth: 360 }}
            maxCount={2}
          />
          <Button icon={<SwapOutlined />} onClick={handleCompare} disabled={compareIds.length !== 2}>
            对比
          </Button>
        </Space>
      </Card>

      <Table<EvalTask>
        rowKey="id"
        columns={columns}
        dataSource={tasks}
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
        scroll={{ x: 800 }}
        size="middle"
      />

      {/* Task Detail Drawer */}
      <Drawer
        title={`评测任务详情 - ${selectedTask?.id?.slice(0, 8) || ''}`}
        open={detailDrawerOpen}
        onClose={() => { setDetailDrawerOpen(false); setSelectedTask(null); }}
        width={560}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : selectedTask ? (
          <div>
            <Card size="small" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={12}><Statistic title="类型" value={selectedTask.eval_type} /></Col>
                <Col span={12}>
                  <Statistic
                    title="状态"
                    value={statusTextMap[selectedTask.status] || selectedTask.status}
                    valueStyle={{ color: selectedTask.status === 'completed' ? '#52c41a' : undefined }}
                  />
                </Col>
              </Row>
              <Row gutter={16} style={{ marginTop: 16 }}>
                <Col span={12}><Statistic title="创建时间" value={formatDate(selectedTask.created_at)} /></Col>
                <Col span={12}>
                  <Statistic title="完成时间" value={selectedTask.completed_at ? formatDate(selectedTask.completed_at) : '-'} />
                </Col>
              </Row>
            </Card>
            <Divider>评测指标</Divider>
            <MetricsCards metrics={selectedTask.metrics} />
          </div>
        ) : null}
      </Drawer>

      {/* Compare Drawer */}
      <Drawer
        title="评测对比"
        open={compareDrawerOpen}
        onClose={() => { setCompareDrawerOpen(false); setComparison(null); }}
        width={720}
      >
        {compareLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : comparison ? (
          <Row gutter={16}>
            <Col span={12}>
              <Card title={`任务 ${comparison.task_1.id.slice(0, 8)}`} size="small">
                <p>类型: {comparison.task_1.eval_type}</p>
                <Divider style={{ margin: '8px 0' }} />
                <MetricsCards metrics={comparison.task_1.metrics} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title={`任务 ${comparison.task_2.id.slice(0, 8)}`} size="small">
                <p>类型: {comparison.task_2.eval_type}</p>
                <Divider style={{ margin: '8px 0' }} />
                <MetricsCards metrics={comparison.task_2.metrics} />
              </Card>
            </Col>
          </Row>
        ) : (
          <Empty description="暂无对比数据" />
        )}
      </Drawer>
    </div>
  );
}

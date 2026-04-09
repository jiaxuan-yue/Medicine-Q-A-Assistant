import { useEffect, useState, useCallback } from 'react';
import {
  Table, Input, Select, Space, Button, Modal, Form, Card, Tag, Drawer,
  Spin, App, Row, Col, Divider, Empty,
} from 'antd';
import { PlusOutlined, SearchOutlined, ApartmentOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { graphApi } from '../api/graph';
import type { GraphEntity, GraphRelation, GraphNode } from '../types';
import GraphViewer from '../components/GraphViewer';

const entityTypeOptions = [
  { label: '症状', value: 'symptom' },
  { label: '中药', value: 'herb' },
  { label: '方剂', value: 'formula' },
  { label: '证型', value: 'syndrome' },
  { label: '疾病', value: 'disease' },
  { label: '穴位', value: 'acupoint' },
  { label: '经络', value: 'meridian' },
];

export default function GraphManagement() {
  const [entities, setEntities] = useState<GraphEntity[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string | undefined>();
  const [selectedEntity, setSelectedEntity] = useState<GraphEntity | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [entityModalOpen, setEntityModalOpen] = useState(false);
  const [relModalOpen, setRelModalOpen] = useState(false);
  const [vizNodes, setVizNodes] = useState<{ id: string; name: string; type: string }[]>([]);
  const [vizEdges, setVizEdges] = useState<{ source: string; target: string; relation: string }[]>([]);
  const [vizLoading, setVizLoading] = useState(false);
  const [entityForm] = Form.useForm();
  const [relForm] = Form.useForm();
  const { message } = App.useApp();

  const fetchEntities = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await graphApi.searchEntities({
        q: searchQuery || undefined,
        entity_type: typeFilter,
      });
      setEntities(data.data);
    } catch {
      message.error('加载实体列表失败');
    } finally {
      setLoading(false);
    }
  }, [searchQuery, typeFilter, message]);

  const fetchVisualization = useCallback(async () => {
    setVizLoading(true);
    try {
      const { data } = await graphApi.getVisualization({
        entity_type: typeFilter,
        limit: 50,
      });
      setVizNodes(data.data.nodes);
      setVizEdges(data.data.edges);
    } catch {
      // silently fail for visualization
    } finally {
      setVizLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    fetchEntities();
    fetchVisualization();
  }, [fetchEntities, fetchVisualization]);

  const handleEntityClick = async (entity: GraphEntity | GraphNode) => {
    setDetailDrawerOpen(true);
    setDetailLoading(true);
    try {
      const { data } = await graphApi.getEntityDetail(entity.name);
      setSelectedEntity(data.data);
    } catch {
      message.error('加载实体详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const handleAddEntity = async (values: { name: string; type: string; aliases?: string; properties?: string }) => {
    try {
      const aliases = values.aliases ? values.aliases.split(',').map((s) => s.trim()).filter(Boolean) : undefined;
      let properties: Record<string, unknown> | undefined;
      if (values.properties) {
        try { properties = JSON.parse(values.properties); } catch { /* ignore */ }
      }
      await graphApi.createEntity({ name: values.name, type: values.type, aliases, properties });
      message.success('实体创建成功');
      setEntityModalOpen(false);
      entityForm.resetFields();
      fetchEntities();
    } catch {
      message.error('创建实体失败');
    }
  };

  const handleAddRelationship = async (values: { from_entity: string; to_entity: string; relation_type: string }) => {
    try {
      await graphApi.createRelationship(values);
      message.success('关系创建成功');
      setRelModalOpen(false);
      relForm.resetFields();
      fetchVisualization();
    } catch {
      message.error('创建关系失败');
    }
  };

  const columns: ColumnsType<GraphEntity> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (name: string, record) => (
        <a onClick={() => handleEntityClick(record)}>{name}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (type: string) => {
        const colorMap: Record<string, string> = {
          symptom: 'red', herb: 'green', formula: 'blue',
          syndrome: 'orange', disease: 'purple', acupoint: 'cyan', meridian: 'magenta',
        };
        return <Tag color={colorMap[type.toLowerCase()] || 'default'}>{type}</Tag>;
      },
    },
    {
      title: '别名',
      dataIndex: 'aliases',
      key: 'aliases',
      ellipsis: true,
      render: (aliases?: string[]) =>
        aliases?.length ? aliases.map((a) => <Tag key={a}>{a}</Tag>) : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => handleEntityClick(record)}>
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>知识图谱管理</h2>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setEntityModalOpen(true)}>
            添加实体
          </Button>
          <Button icon={<ApartmentOutlined />} onClick={() => setRelModalOpen(true)}>
            添加关系
          </Button>
        </Space>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          placeholder="搜索实体名称"
          allowClear
          onSearch={setSearchQuery}
          onChange={(e) => !e.target.value && setSearchQuery('')}
          style={{ width: 240 }}
          prefix={<SearchOutlined />}
        />
        <Select
          placeholder="实体类型"
          allowClear
          options={entityTypeOptions}
          onChange={setTypeFilter}
          style={{ width: 140 }}
        />
      </Space>

      <Table<GraphEntity>
        rowKey="name"
        columns={columns}
        dataSource={entities}
        loading={loading}
        pagination={{ showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
        scroll={{ x: 600 }}
        size="middle"
      />

      <Divider />
      <h3>图谱可视化</h3>
      {vizLoading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : (
        <GraphViewer nodes={vizNodes} edges={vizEdges} onNodeClick={handleEntityClick} />
      )}

      {/* Entity Detail Drawer */}
      <Drawer
        title={selectedEntity?.name || '实体详情'}
        open={detailDrawerOpen}
        onClose={() => { setDetailDrawerOpen(false); setSelectedEntity(null); }}
        width={480}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : selectedEntity ? (
          <div>
            <Card size="small" title="基本信息" style={{ marginBottom: 16 }}>
              <p><strong>名称：</strong>{selectedEntity.name}</p>
              <p><strong>类型：</strong><Tag>{selectedEntity.type}</Tag></p>
              {selectedEntity.aliases?.length ? (
                <p><strong>别名：</strong>{selectedEntity.aliases.map((a) => <Tag key={a}>{a}</Tag>)}</p>
              ) : null}
              {selectedEntity.properties && Object.keys(selectedEntity.properties).length > 0 && (
                <div>
                  <strong>属性：</strong>
                  <pre style={{ fontSize: 12, marginTop: 4 }}>
                    {JSON.stringify(selectedEntity.properties, null, 2)}
                  </pre>
                </div>
              )}
            </Card>
            <Card size="small" title="关联关系">
              {selectedEntity.neighbors?.length ? (
                selectedEntity.neighbors.map((rel: GraphRelation, idx: number) => (
                  <Row key={idx} style={{ marginBottom: 8 }}>
                    <Col span={24}>
                      <Tag color="blue">{rel.from_entity}</Tag>
                      <span style={{ margin: '0 8px' }}>—{rel.relation_type}→</span>
                      <Tag color="green">{rel.to_entity}</Tag>
                    </Col>
                  </Row>
                ))
              ) : (
                <Empty description="暂无关联关系" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          </div>
        ) : null}
      </Drawer>

      {/* Add Entity Modal */}
      <Modal
        title="添加实体"
        open={entityModalOpen}
        onCancel={() => { setEntityModalOpen(false); entityForm.resetFields(); }}
        onOk={() => entityForm.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={entityForm} layout="vertical" onFinish={handleAddEntity}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入实体名称' }]}>
            <Input placeholder="例如：麻黄" />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择实体类型' }]}>
            <Select placeholder="选择类型" options={entityTypeOptions} />
          </Form.Item>
          <Form.Item name="aliases" label="别名（逗号分隔）">
            <Input placeholder="例如：龙沙,卑相" />
          </Form.Item>
          <Form.Item name="properties" label="属性（JSON格式）">
            <Input.TextArea rows={3} placeholder='例如：{"性味":"辛温","归经":"肺、膀胱经"}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* Add Relationship Modal */}
      <Modal
        title="添加关系"
        open={relModalOpen}
        onCancel={() => { setRelModalOpen(false); relForm.resetFields(); }}
        onOk={() => relForm.submit()}
        okText="创建"
        cancelText="取消"
      >
        <Form form={relForm} layout="vertical" onFinish={handleAddRelationship}>
          <Form.Item name="from_entity" label="起始实体" rules={[{ required: true, message: '请输入起始实体名称' }]}>
            <Input placeholder="实体名称" />
          </Form.Item>
          <Form.Item name="to_entity" label="目标实体" rules={[{ required: true, message: '请输入目标实体名称' }]}>
            <Input placeholder="实体名称" />
          </Form.Item>
          <Form.Item name="relation_type" label="关系类型" rules={[{ required: true, message: '请输入关系类型' }]}>
            <Input placeholder="例如：主治、配伍、组成" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

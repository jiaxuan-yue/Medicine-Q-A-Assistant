import { useEffect } from 'react';
import { Form, Input, InputNumber, Switch, Button, Card, Divider, App } from 'antd';
import { SaveOutlined, UndoOutlined } from '@ant-design/icons';
import { configApi } from '../api/config';
import type { ModelConfigData } from '../types';

export default function ModelConfig() {
  const [form] = Form.useForm<ModelConfigData>();
  const { message } = App.useApp();

  useEffect(() => {
    const config = configApi.getConfig();
    form.setFieldsValue(config);
  }, [form]);

  const handleSave = (values: ModelConfigData) => {
    configApi.saveConfig(values);
    message.success('配置已保存');
  };

  const handleReset = () => {
    const defaults = configApi.getDefaultConfig();
    form.setFieldsValue(defaults);
    configApi.saveConfig(defaults);
    message.success('已恢复默认配置');
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>模型配置</h2>
        <Button icon={<UndoOutlined />} onClick={handleReset}>
          恢复默认
        </Button>
      </div>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSave}
        style={{ maxWidth: 720 }}
      >
        <Card title="检索参数" size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="top_k" label="Top K（检索返回数量）" rules={[{ required: true }]}>
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="rerank_k" label="Rerank K（重排序保留数量）" rules={[{ required: true }]}>
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="rrf_k" label="RRF K（倒数排序融合参数）" rules={[{ required: true }]}>
            <InputNumber min={1} max={200} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="graph_max_hops" label="图谱最大跳数" rules={[{ required: true }]}>
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card title="功能开关" size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="query_rewrite_enabled" label="查询改写" valuePropName="checked">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item name="graph_recall_enabled" label="图谱召回" valuePropName="checked">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
          <Form.Item name="reranker_enabled" label="重排序" valuePropName="checked">
            <Switch checkedChildren="开启" unCheckedChildren="关闭" />
          </Form.Item>
        </Card>

        <Card title="模型选择" size="small" style={{ marginBottom: 16 }}>
          <Form.Item name="llm_model" label="LLM 模型" rules={[{ required: true, message: '请输入LLM模型名称' }]}>
            <Input placeholder="例如：qwen-plus" />
          </Form.Item>
          <Form.Item name="embedding_model" label="Embedding 模型" rules={[{ required: true, message: '请输入Embedding模型名称' }]}>
            <Input placeholder="例如：bge-large-zh-v1.5" />
          </Form.Item>
          <Form.Item name="reranker_model" label="Reranker 模型" rules={[{ required: true, message: '请输入Reranker模型名称' }]}>
            <Input placeholder="例如：bge-reranker-v2-m3" />
          </Form.Item>
        </Card>

        <Divider />

        <Form.Item>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />} size="large">
            保存配置
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}

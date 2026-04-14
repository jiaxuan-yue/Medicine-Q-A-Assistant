import { Collapse, Card, List, Tag, Typography, Steps, Empty } from 'antd';
import {
  SearchOutlined,
  EditOutlined,
  DatabaseOutlined,
  ApartmentOutlined,
  MergeCellsOutlined,
  SortAscendingOutlined,
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

interface RetrievalStage {
  name: string;
  data: unknown;
}

interface RetrievalTraceViewerProps {
  stages?: RetrievalStage[];
}

const STAGE_ICONS: Record<string, React.ReactNode> = {
  query: <SearchOutlined />,
  rewrite: <EditOutlined />,
  sparse: <DatabaseOutlined />,
  dense: <DatabaseOutlined />,
  graph: <ApartmentOutlined />,
  fused: <MergeCellsOutlined />,
  reranked: <SortAscendingOutlined />,
};

const STAGE_LABELS: Record<string, string> = {
  query: '原始查询',
  rewrite: '查询改写',
  sparse: '稀疏检索结果',
  dense: '稠密检索结果',
  graph: '图谱召回结果',
  fused: '融合结果',
  reranked: '重排序结果',
};

function renderStageData(data: unknown) {
  if (typeof data === 'string') {
    return <Paragraph style={{ margin: 0 }}>{data}</Paragraph>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) return <Empty description="无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    return (
      <List
        size="small"
        dataSource={data}
        renderItem={(item: Record<string, unknown>, idx: number) => (
          <List.Item key={idx}>
            <div style={{ width: '100%' }}>
              <Text strong>{(item.title as string) || (item.content as string)?.slice(0, 60) || `#${idx + 1}`}</Text>
              {item.score !== undefined && (
                <Tag color="blue" style={{ marginLeft: 8 }}>
                  score: {Number(item.score).toFixed(4)}
                </Tag>
              )}
              {Boolean(item.source) && (
                <Tag color="green" style={{ marginLeft: 4 }}>
                  {String(item.source)}
                </Tag>
              )}
              {typeof item.content === 'string' && (
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 2 }}
                  style={{ margin: '4px 0 0', fontSize: 12 }}
                >
                  {item.content}
                </Paragraph>
              )}
            </div>
          </List.Item>
        )}
      />
    );
  }
  if (data && typeof data === 'object') {
    return (
      <pre style={{ margin: 0, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
        {JSON.stringify(data, null, 2)}
      </pre>
    );
  }
  return <Text type="secondary">-</Text>;
}

export default function RetrievalTraceViewer({ stages }: RetrievalTraceViewerProps) {
  if (!stages || stages.length === 0) {
    return (
      <Card>
        <Empty description="暂无检索追踪数据" />
      </Card>
    );
  }

  const stepsItems = stages.map((stage) => ({
    title: STAGE_LABELS[stage.name] || stage.name,
    icon: STAGE_ICONS[stage.name],
    status: 'finish' as const,
  }));

  const collapseItems = stages.map((stage, idx) => ({
    key: String(idx),
    label: (
      <span>
        {STAGE_ICONS[stage.name] || <SearchOutlined />}
        <span style={{ marginLeft: 8 }}>{STAGE_LABELS[stage.name] || stage.name}</span>
      </span>
    ),
    children: renderStageData(stage.data),
  }));

  return (
    <div>
      <Steps
        items={stepsItems}
        size="small"
        style={{ marginBottom: 16 }}
      />
      <Collapse
        defaultActiveKey={stages.map((_, i) => String(i))}
        items={collapseItems}
      />
    </div>
  );
}

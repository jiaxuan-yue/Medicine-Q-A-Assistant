import React from 'react';
import { Collapse, Tag, Typography, Empty } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import type { Citation } from '../types';

const { Paragraph, Text } = Typography;

interface CitationPanelProps {
  citations: Citation[];
}

const CitationPanel: React.FC<CitationPanelProps> = ({ citations }) => {
  if (!citations || citations.length === 0) return null;

  const items = citations.map((cite, index) => {
    const excerptText = cite.excerpt || cite.text || '';
    const shortExcerpt = excerptText.length > 100
      ? excerptText.slice(0, 100) + '...'
      : excerptText;

    return {
      key: String(index),
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BookOutlined style={{ color: '#1890ff' }} />
          <Text strong style={{ flex: 1 }}>
            {cite.doc_title || '未知文献'}
          </Text>
          {cite.chunk_id && (
            <Tag color="blue" style={{ marginRight: 0 }}>
              {cite.chunk_id}
            </Tag>
          )}
        </div>
      ),
      children: (
        <div>
          <Paragraph
            style={{
              background: '#fafafa',
              padding: 12,
              borderRadius: 6,
              borderLeft: '3px solid #1890ff',
              margin: 0,
            }}
          >
            {excerptText}
          </Paragraph>
          <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {cite.doc_id && (
              <Tag color="geekblue">文献ID: {cite.doc_id}</Tag>
            )}
            {cite.location && (
              <Tag color="cyan">位置: {cite.location}</Tag>
            )}
          </div>
        </div>
      ),
      extra: (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {shortExcerpt}
        </Text>
      ),
    };
  });

  return (
    <div className="citation-panel" style={{ marginTop: 8 }}>
      <Text type="secondary" style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>
        📚 引用来源 ({citations.length})
      </Text>
      <Collapse
        size="small"
        items={items}
        bordered={false}
        style={{ background: 'transparent' }}
      />
    </div>
  );
};

export default CitationPanel;

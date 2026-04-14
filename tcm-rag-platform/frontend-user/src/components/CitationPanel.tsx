import React from 'react';
import { Collapse, Tag, Typography } from 'antd';
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
        <div className="citation-panel-item-title">
          <BookOutlined style={{ color: 'var(--cinnabar)' }} />
          <div className="citation-panel-item-copy">
            <Text strong>{cite.doc_title || '未知文献'}</Text>
            <span>{shortExcerpt}</span>
          </div>
          {cite.chunk_id && (
            <Tag color="volcano" style={{ marginRight: 0 }}>
              {cite.chunk_id}
            </Tag>
          )}
        </div>
      ),
      children: (
        <div className="citation-panel-body">
          <Paragraph className="citation-panel-excerpt">
            {excerptText}
          </Paragraph>
          <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {cite.doc_id && (
              <Tag color="geekblue">文献ID: {cite.doc_id}</Tag>
            )}
            {cite.location && (
              <Tag color="cyan">位置: {cite.location}</Tag>
            )}
          </div>
        </div>
      ),
    };
  });

  return (
    <div className="citation-panel">
      <div className="citation-panel-title">
        <BookOutlined />
        <Text type="secondary">引用依据</Text>
        <em>{citations.length} 条</em>
      </div>
      <Collapse
        size="small"
        items={items}
        bordered={false}
      />
    </div>
  );
};

export default CitationPanel;

import React, { useState } from 'react';
import { Button, Tooltip, Modal, Input, message, Space } from 'antd';
import {
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
  WarningOutlined,
} from '@ant-design/icons';
import { feedbackApi } from '../api/feedback';
import type { FeedbackData } from '../types';

interface FeedbackActionsProps {
  messageId: number;
}

const FeedbackActions: React.FC<FeedbackActionsProps> = ({ messageId }) => {
  const [liked, setLiked] = useState(false);
  const [disliked, setDisliked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportSubmitting, setReportSubmitting] = useState(false);

  const handleFeedback = async (type: FeedbackData['feedback_type']) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await feedbackApi.submit({ message_id: messageId, feedback_type: type });
      if (type === 'like') {
        setLiked(true);
        setDisliked(false);
        message.success('感谢您的反馈！');
      } else if (type === 'dislike') {
        setDisliked(true);
        setLiked(false);
        message.success('感谢您的反馈，我们会持续改进');
      }
    } catch {
      message.error('提交反馈失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReportSubmit = async () => {
    if (!reportContent.trim()) {
      message.warning('请输入问题描述');
      return;
    }
    setReportSubmitting(true);
    try {
      await feedbackApi.submit({
        message_id: messageId,
        feedback_type: 'correction',
        content: reportContent.trim(),
      });
      message.success('问题已提交，感谢您的反馈！');
      setReportOpen(false);
      setReportContent('');
    } catch {
      message.error('提交失败，请稍后重试');
    } finally {
      setReportSubmitting(false);
    }
  };

  return (
    <>
      <Space size={4} className="feedback-actions">
        <Tooltip title="有帮助">
          <Button
            type="text"
            size="small"
            icon={liked ? <LikeFilled style={{ color: '#1890ff' }} /> : <LikeOutlined />}
            onClick={() => handleFeedback('like')}
            disabled={liked || submitting}
          />
        </Tooltip>
        <Tooltip title="没有帮助">
          <Button
            type="text"
            size="small"
            icon={disliked ? <DislikeFilled style={{ color: '#ff4d4f' }} /> : <DislikeOutlined />}
            onClick={() => handleFeedback('dislike')}
            disabled={disliked || submitting}
          />
        </Tooltip>
        <Tooltip title="反馈问题">
          <Button
            type="text"
            size="small"
            icon={<WarningOutlined />}
            onClick={() => setReportOpen(true)}
          />
        </Tooltip>
      </Space>

      <Modal
        title="反馈问题"
        open={reportOpen}
        onCancel={() => {
          setReportOpen(false);
          setReportContent('');
        }}
        onOk={handleReportSubmit}
        confirmLoading={reportSubmitting}
        okText="提交"
        cancelText="取消"
      >
        <p style={{ marginBottom: 8, color: '#666' }}>
          请描述您发现的问题，我们会尽快改进：
        </p>
        <Input.TextArea
          value={reportContent}
          onChange={(e) => setReportContent(e.target.value)}
          placeholder="例如：回答内容有误、引用来源不准确..."
          rows={4}
          maxLength={500}
          showCount
        />
      </Modal>
    </>
  );
};

export default FeedbackActions;

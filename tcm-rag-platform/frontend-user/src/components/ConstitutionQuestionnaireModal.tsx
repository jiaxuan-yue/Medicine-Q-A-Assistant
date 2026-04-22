import React, { useEffect, useState } from 'react';
import { Modal, Radio, Progress, Tag, Button } from 'antd';
import type { CaseProfilePayload } from '../types';
import {
  buildQuestionnairePayload,
  CONSTITUTION_OPTIONS,
  CONSTITUTION_QUESTIONNAIRE,
  QUESTIONNAIRE_OPTIONS,
  type ConstitutionQuestionnaireAnswers,
} from '../utils/constitutionQuestionnaire';
import './CaseProfiles.css';

interface ConstitutionQuestionnaireModalProps {
  open: boolean;
  onClose: () => void;
  onApply: (payload: Partial<CaseProfilePayload>) => Promise<void> | void;
}

const ConstitutionQuestionnaireModal: React.FC<ConstitutionQuestionnaireModalProps> = ({
  open,
  onClose,
  onApply,
}) => {
  const [answers, setAnswers] = useState<ConstitutionQuestionnaireAnswers>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setAnswers({});
  }, [open]);

  const answeredCount = CONSTITUTION_QUESTIONNAIRE.filter((question) => typeof answers[question.id] === 'number').length;
  const progress = Math.round((answeredCount / CONSTITUTION_QUESTIONNAIRE.length) * 100);
  const questionnaireCompleted = answeredCount === CONSTITUTION_QUESTIONNAIRE.length;
  const previewPayload = questionnaireCompleted ? buildQuestionnairePayload(answers) : null;
  const primary = previewPayload?.constitution_primary || '待计算';
  const secondary = previewPayload?.constitution_secondary || [];

  const handleSubmit = async () => {
    if (!previewPayload) {
      return;
    }
    setSaving(true);
    try {
      await onApply(previewPayload);
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={saving ? undefined : onClose}
      footer={null}
      width={980}
      centered
      className="caseprofiles-modal constitution-questionnaire-modal"
      title={null}
      destroyOnHidden
    >
      <div className="caseprofiles-shell">
        <div className="caseprofiles-hero caseprofiles-hero-compact">
          <div className="caseprofiles-badge">体质问卷</div>
          <h2>用一组生活化问题，把九体质结果回写到角色档案。</h2>
          <p>这份问卷适合做轻量体质初筛。提交后会自动生成主体质、兼具体质、九体质分数和测评日期。</p>
          <div className="questionnaire-progress-row">
            <div>
              <strong>完成度 {progress}%</strong>
              <span>{answeredCount}/{CONSTITUTION_QUESTIONNAIRE.length} 题</span>
            </div>
            <Progress percent={progress} showInfo={false} strokeColor="#285d4c" />
          </div>
          <div className="questionnaire-preview-tags">
            <Tag color="green">预计主体质：{primary}</Tag>
            {secondary.map((item) => (
              <Tag key={item} color="gold">
                兼具体质：{item}
              </Tag>
            ))}
            {!secondary.length && <Tag>兼具体质待计算</Tag>}
            {!questionnaireCompleted && <Tag>完成全部题目后生成结果</Tag>}
          </div>
        </div>

        <div className="questionnaire-legend">
          {QUESTIONNAIRE_OPTIONS.map((option) => (
            <span key={option.value}>{option.label} {option.value}</span>
          ))}
        </div>

        <div className="questionnaire-grid">
          {CONSTITUTION_OPTIONS.map((constitution) => {
            const items = CONSTITUTION_QUESTIONNAIRE.filter((question) => question.constitution === constitution);
            return (
              <section key={constitution} className="questionnaire-card">
                <div className="questionnaire-card-header">
                  <h3>{constitution}</h3>
                  <Tag bordered={false}>{items.length} 题</Tag>
                </div>
                {items.map((question) => (
                  <div key={question.id} className="questionnaire-item">
                    <div className="questionnaire-item-copy">
                      <strong>{question.prompt}</strong>
                      <span>{question.hint}</span>
                    </div>
                    <Radio.Group
                      className="questionnaire-radio-group"
                      value={answers[question.id]}
                      onChange={(event) =>
                        setAnswers((current) => ({
                          ...current,
                          [question.id]: event.target.value,
                        }))
                      }
                    >
                      {QUESTIONNAIRE_OPTIONS.map((option) => (
                        <Radio.Button key={option.value} value={option.value}>
                          {option.label}
                        </Radio.Button>
                      ))}
                    </Radio.Group>
                  </div>
                ))}
              </section>
            );
          })}
        </div>

        <div className="caseprofiles-actions caseprofiles-actions-spread">
          <Button onClick={onClose} disabled={saving}>
            先不做
          </Button>
          <Button type="primary" loading={saving} onClick={handleSubmit} disabled={!questionnaireCompleted}>
            回写到角色档案
          </Button>
        </div>
      </div>
    </Modal>
  );
};

export default ConstitutionQuestionnaireModal;

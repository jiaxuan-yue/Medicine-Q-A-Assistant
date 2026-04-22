import React from 'react';
import { Button, Empty, Modal, Tag, message } from 'antd';
import { PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useCaseProfilesStore } from '../stores/caseProfilesStore';
import { useChatStore } from '../stores/chatStore';
import { getApiErrorMessage } from '../utils/apiError';
import type { CaseProfile } from '../types';
import { hasQuestionnaireResult } from '../utils/constitutionQuestionnaire';
import './CaseProfiles.css';

const buildRoleSignals = (profile: CaseProfile) => {
  const signals: Array<{ label: string; color?: string }> = [];
  if (profile.constitution_primary) {
    signals.push({ label: `主体质：${profile.constitution_primary}`, color: 'green' });
  }
  signals.push(
    hasQuestionnaireResult(profile)
      ? { label: '问卷结果已回写', color: 'gold' }
      : { label: '待完成体质问卷' }
  );
  if (profile.tongue_coating) {
    signals.push({ label: `舌苔：${profile.tongue_coating}` });
  }
  if (profile.constitution_assessed_at) {
    signals.push({ label: `测评：${profile.constitution_assessed_at.slice(0, 10)}` });
  }
  return signals.slice(0, 4);
};

const CaseProfilePickerModal: React.FC = () => {
  const navigate = useNavigate();
  const { createSession } = useChatStore();
  const {
    profiles,
    pickerOpen,
    closePicker,
    openManager,
    activeProfileId,
    setActiveProfileId,
  } = useCaseProfilesStore();

  const handleStart = async () => {
    if (!activeProfileId) {
      message.warning('请先选择一个角色');
      return;
    }

    try {
      const session = await createSession(activeProfileId);
      closePicker();
      navigate(`/chats/${session.session_id}`);
    } catch (error) {
      message.error(getApiErrorMessage(error, '创建对话失败'));
    }
  };

  return (
    <Modal
      open={pickerOpen}
      onCancel={closePicker}
      footer={null}
      centered
      width={860}
      className="caseprofiles-modal"
      title={null}
    >
      <div className="caseprofiles-shell">
        <div className="caseprofiles-hero caseprofiles-hero-compact">
          <div className="caseprofiles-badge">新建对话</div>
          <h2>为这一轮问答选择对应角色。</h2>
          <p>每个角色代表一个独立的基础档案。开始对话后，这份基础信息会自动带入整个会话。</p>
        </div>

        {profiles.length === 0 ? (
          <Empty
            description="还没有角色档案，请先创建一个"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => openManager()}>
              新建角色
            </Button>
          </Empty>
        ) : (
          <>
            <div className="caseprofiles-card-grid">
              {profiles.map((profile) => {
                const selected = profile.id === activeProfileId;
                return (
                  <button
                    key={profile.id}
                    type="button"
                    className={`caseprofiles-card ${selected ? 'is-selected' : ''}`}
                    onClick={() => setActiveProfileId(profile.id)}
                  >
                    <div className="caseprofiles-card-header">
                      <strong>{profile.profile_name}</strong>
                      {selected && <CheckCircleOutlined />}
                    </div>
                    <p>{profile.summary || '补充身高、体重、既往病史、当前用药等基础信息。'}</p>
                    <div className="caseprofiles-card-tags">
                      {buildRoleSignals(profile).map((tag) => (
                        <Tag key={`${profile.id}-${tag.label}`} color={tag.color}>
                          {tag.label}
                        </Tag>
                      ))}
                      {(profile.tags || []).map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="caseprofiles-actions caseprofiles-actions-spread">
              <Button icon={<PlusOutlined />} onClick={() => openManager()}>
                新增角色
              </Button>
              <Button type="primary" onClick={handleStart}>
                以当前角色开始对话
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

export default CaseProfilePickerModal;

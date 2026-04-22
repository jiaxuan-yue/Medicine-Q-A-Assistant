import React, { useEffect, useState } from 'react';
import { Button, Form, Image, Input, InputNumber, Modal, Progress, Radio, Select, Tag, Upload, message } from 'antd';
import { LoadingOutlined, PictureOutlined } from '@ant-design/icons';
import type { RcFile } from 'antd/es/upload';
import { useCaseProfilesStore } from '../stores/caseProfilesStore';
import { getApiErrorMessage } from '../utils/apiError';
import type { CaseProfilePayload } from '../types';
import ConstitutionQuestionnaireModal from './ConstitutionQuestionnaireModal';
import { hasQuestionnaireResult } from '../utils/constitutionQuestionnaire';
import './CaseProfiles.css';

const TAG_OPTIONS = ['本人', '家人', '儿童', '老人', '慢病随访', '术后调理'];
const CONSTITUTION_SCORE_FIELDS = [
  { name: 'constitution_pinghe_score', label: '平和' },
  { name: 'constitution_qixu_score', label: '气虚' },
  { name: 'constitution_yangxu_score', label: '阳虚' },
  { name: 'constitution_yinxu_score', label: '阴虚' },
  { name: 'constitution_tanshi_score', label: '痰湿' },
  { name: 'constitution_shire_score', label: '湿热' },
  { name: 'constitution_xueyu_score', label: '血瘀' },
  { name: 'constitution_qiyu_score', label: '气郁' },
  { name: 'constitution_tebing_score', label: '特禀' },
] as const;
const TONGUE_ACCEPT_TYPES = ['image/png', 'image/jpeg'];
const TONGUE_MAX_SIZE_MB = 8;

const CaseProfileManagerModal: React.FC = () => {
  const [form] = Form.useForm<CaseProfilePayload>();
  const [questionnaireOpen, setQuestionnaireOpen] = useState(false);
  const [tongueUploading, setTongueUploading] = useState(false);
  const watchedValues = (Form.useWatch([], form) || {}) as Partial<CaseProfilePayload>;
  const {
    profiles,
    managerOpen,
    editingProfile,
    saving,
    createProfile,
    updateProfile,
    uploadTongueImage,
    closeManager,
  } = useCaseProfilesStore();

  useEffect(() => {
    if (!managerOpen) {
      return;
    }
    form.setFieldsValue({
      profile_name: editingProfile?.profile_name || undefined,
      gender: editingProfile?.gender || undefined,
      age: editingProfile?.age || undefined,
      height_cm: editingProfile?.height_cm || undefined,
      weight_kg: editingProfile?.weight_kg || undefined,
      medical_history: editingProfile?.medical_history || undefined,
      allergy_history: editingProfile?.allergy_history || undefined,
      current_medications: editingProfile?.current_medications || undefined,
      menstrual_history: editingProfile?.menstrual_history || undefined,
      notes: editingProfile?.notes || undefined,
      constitution_primary: editingProfile?.constitution_primary || undefined,
      constitution_secondary: editingProfile?.constitution_secondary || [],
      constitution_pinghe_score: editingProfile?.constitution_pinghe_score ?? undefined,
      constitution_qixu_score: editingProfile?.constitution_qixu_score ?? undefined,
      constitution_yangxu_score: editingProfile?.constitution_yangxu_score ?? undefined,
      constitution_yinxu_score: editingProfile?.constitution_yinxu_score ?? undefined,
      constitution_tanshi_score: editingProfile?.constitution_tanshi_score ?? undefined,
      constitution_shire_score: editingProfile?.constitution_shire_score ?? undefined,
      constitution_xueyu_score: editingProfile?.constitution_xueyu_score ?? undefined,
      constitution_qiyu_score: editingProfile?.constitution_qiyu_score ?? undefined,
      constitution_tebing_score: editingProfile?.constitution_tebing_score ?? undefined,
      constitution_assessed_at: editingProfile?.constitution_assessed_at || undefined,
      constitution_reassessment_cycle_days: editingProfile?.constitution_reassessment_cycle_days ?? 90,
      tongue_image_url: editingProfile?.tongue_image_url || undefined,
      tongue_color: editingProfile?.tongue_color || undefined,
      tongue_coating: editingProfile?.tongue_coating || undefined,
      tongue_shape: editingProfile?.tongue_shape || undefined,
      tongue_constitution_hint: editingProfile?.tongue_constitution_hint || undefined,
      tongue_raw_description: editingProfile?.tongue_raw_description || undefined,
      tags: editingProfile?.tags || [],
    });
  }, [editingProfile, form, managerOpen]);

  const questionnaireDone = hasQuestionnaireResult(watchedValues);
  const questionnairePrimary = watchedValues.constitution_primary;
  const questionnaireAssessedAt = watchedValues.constitution_assessed_at;
  const questionnaireSecondary = watchedValues.constitution_secondary || [];
  const tongueImageUrl = watchedValues.tongue_image_url || null;
  const tongueSignals = [
    watchedValues.tongue_color ? `舌色：${watchedValues.tongue_color}` : null,
    watchedValues.tongue_coating ? `舌苔：${watchedValues.tongue_coating}` : null,
    watchedValues.tongue_shape ? `舌形：${watchedValues.tongue_shape}` : null,
    watchedValues.tongue_constitution_hint ? `倾向：${watchedValues.tongue_constitution_hint}` : null,
  ].filter(Boolean) as string[];

  const buildFormSnapshot = () => ({
    ...form.getFieldsValue(true),
  }) as CaseProfilePayload;

  const handleQuestionnaireApply = async (payload: Partial<CaseProfilePayload>) => {
    const mergedValues = {
      ...buildFormSnapshot(),
      ...payload,
    } as CaseProfilePayload;
    form.setFieldsValue(mergedValues);

    if (editingProfile) {
      try {
        const profile = await updateProfile(editingProfile.id, mergedValues, { keepManagerOpen: true });
        form.setFieldsValue({
          ...mergedValues,
          constitution_primary: profile.constitution_primary || undefined,
          constitution_secondary: profile.constitution_secondary || [],
          constitution_assessed_at: profile.constitution_assessed_at || undefined,
        });
        message.success('体质问卷结果已同步到角色档案');
      } catch (error) {
        message.error(getApiErrorMessage(error, '问卷结果已回填到表单，请点击保存角色'));
      }
      return;
    }

    message.success('体质问卷结果已回填到档案表单，保存角色后生效');
  };

  const handleTongueBeforeUpload = async (file: RcFile) => {
    if (!TONGUE_ACCEPT_TYPES.includes(file.type)) {
      message.error('仅支持 PNG 或 JPG 格式的舌像');
      return Upload.LIST_IGNORE;
    }
    if (file.size / 1024 / 1024 > TONGUE_MAX_SIZE_MB) {
      message.error(`舌像大小不能超过 ${TONGUE_MAX_SIZE_MB}MB`);
      return Upload.LIST_IGNORE;
    }
    if (!editingProfile) {
      message.warning('请先创建角色，再上传舌像');
      return Upload.LIST_IGNORE;
    }

    setTongueUploading(true);
    try {
      const profile = await uploadTongueImage(editingProfile.id, file, { keepManagerOpen: true });
      form.setFieldsValue({
        tongue_image_url: profile.tongue_image_url || undefined,
        tongue_color: profile.tongue_color || undefined,
        tongue_coating: profile.tongue_coating || undefined,
        tongue_shape: profile.tongue_shape || undefined,
        tongue_constitution_hint: profile.tongue_constitution_hint || undefined,
        tongue_raw_description: profile.tongue_raw_description || undefined,
      });
      message.success('舌像已上传到角色档案');
    } catch (error) {
      message.error(getApiErrorMessage(error, '舌像上传失败'));
    } finally {
      setTongueUploading(false);
    }

    return Upload.LIST_IGNORE;
  };

  const handleSubmit = async () => {
    try {
      const validatedValues = await form.validateFields();
      const values = {
        ...buildFormSnapshot(),
        ...validatedValues,
      } as CaseProfilePayload;
      if (editingProfile) {
        await updateProfile(editingProfile.id, values);
        message.success('角色档案已更新');
      } else {
        await createProfile(values);
        message.success('角色档案已创建');
      }
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      message.error(getApiErrorMessage(error, '保存角色档案失败'));
    }
  };

  return (
    <Modal
      open={managerOpen}
      footer={null}
      onCancel={profiles.length > 0 ? closeManager : undefined}
      maskClosable={profiles.length > 0}
      keyboard={profiles.length > 0}
      closable={profiles.length > 0}
      centered
      width={920}
      className="caseprofiles-modal"
      destroyOnHidden={false}
      title={null}
    >
      <div className="caseprofiles-shell">
        <div className="caseprofiles-hero">
          <div className="caseprofiles-badge">{editingProfile ? '编辑角色' : '建立角色档案'}</div>
          <h2>为这次问答定义一个清晰的就诊对象。</h2>
          <p>
            一个账号下面可以维护多个角色，比如本人、母亲、父亲或孩子。后续每次新建对话时，都从这些角色中选择一个进入会话。
          </p>
        </div>

        <Form<CaseProfilePayload>
          form={form}
          layout="vertical"
          className="caseprofiles-form"
          initialValues={{
            tags: [],
            constitution_secondary: [],
            constitution_reassessment_cycle_days: 90,
          }}
        >
          <div className="caseprofiles-grid caseprofiles-grid-4">
            <Form.Item label="角色名称" name="profile_name" rules={[{ required: true, message: '请输入角色名称' }]}>
              <Input placeholder="例如：本人 / 母亲 / 父亲 / 孩子" />
            </Form.Item>

            <Form.Item label="性别" name="gender" rules={[{ required: true, message: '请选择性别' }]}>
              <Radio.Group optionType="button" buttonStyle="solid">
                <Radio.Button value="男">男</Radio.Button>
                <Radio.Button value="女">女</Radio.Button>
              </Radio.Group>
            </Form.Item>

            <Form.Item label="年龄" name="age" rules={[{ required: true, message: '请输入年龄' }]}>
              <InputNumber min={1} max={120} style={{ width: '100%' }} placeholder="例如 32" />
            </Form.Item>

            <Form.Item label="标签" name="tags">
              <Select
                mode="multiple"
                options={TAG_OPTIONS.map((item) => ({ value: item, label: item }))}
                placeholder="可选"
              />
            </Form.Item>
          </div>

          <div className="caseprofiles-grid caseprofiles-grid-2">
            <Form.Item label="身高(cm)" name="height_cm">
              <InputNumber min={1} max={260} style={{ width: '100%' }} placeholder="例如 168" />
            </Form.Item>

            <Form.Item label="体重(kg)" name="weight_kg">
              <InputNumber min={1} max={300} style={{ width: '100%' }} placeholder="例如 58" />
            </Form.Item>
          </div>

          <div className="caseprofiles-grid caseprofiles-grid-2">
            <Form.Item label="既往病史" name="medical_history">
              <Input.TextArea rows={3} placeholder="例如：高血压 5 年、糖尿病、甲状腺结节等" />
            </Form.Item>

            <Form.Item label="过敏史" name="allergy_history">
              <Input.TextArea rows={3} placeholder="例如：青霉素过敏、海鲜过敏；没有可留空" />
            </Form.Item>

            <Form.Item label="当前用药" name="current_medications">
              <Input.TextArea rows={3} placeholder="例如：降压药、胃药、中成药等" />
            </Form.Item>

            <Form.Item label="月经/孕产信息" name="menstrual_history">
              <Input.TextArea rows={3} placeholder="女性角色可填写；其他情况可留空" />
            </Form.Item>
          </div>

          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} placeholder="例如：近期手术后恢复期、工作压力大、常熬夜等" />
          </Form.Item>

          <div className="caseprofiles-section-heading">
            <h3>长期体质画像</h3>
            <p>这里的字段会作为长期底盘进入后续问答，不和会话里的临时症状混在一起。</p>
            <div className="caseprofiles-inline-actions">
              <div className="caseprofiles-inline-tags">
                {questionnaireDone ? (
                  <>
                    <Tag color="green">问卷结果已回写</Tag>
                    {questionnairePrimary && (
                      <Tag color="gold">主体质：{questionnairePrimary}</Tag>
                    )}
                    {questionnaireAssessedAt && <Tag>测评：{questionnaireAssessedAt}</Tag>}
                  </>
                ) : (
                  <Tag>待完成体质问卷</Tag>
                )}
              </div>
              <Button type={questionnaireDone ? 'default' : 'primary'} onClick={() => setQuestionnaireOpen(true)}>
                {questionnaireDone ? '重新做问卷' : '开始体质问卷'}
              </Button>
            </div>
          </div>

          <div className="caseprofiles-readonly-panel">
            <div className="caseprofiles-readonly-grid caseprofiles-readonly-grid-2">
              <div className="caseprofiles-summary-card">
                <span>主体质</span>
                <strong>{questionnairePrimary || '待问卷回写'}</strong>
                <p>这部分由体质问卷结果驱动，不再支持手动填写。</p>
              </div>
              <div className="caseprofiles-summary-card">
                <span>测评节奏</span>
                <strong>{questionnaireAssessedAt || '尚未测评'}</strong>
                <p>复评周期 {watchedValues.constitution_reassessment_cycle_days || 90} 天</p>
              </div>
              <div className="caseprofiles-summary-card">
                <span>兼具体质</span>
                <div className="caseprofiles-inline-tags">
                  {questionnaireSecondary.length ? (
                    questionnaireSecondary.map((item) => <Tag key={item}>{item}</Tag>)
                  ) : (
                    <Tag>待问卷判断</Tag>
                  )}
                </div>
              </div>
            </div>

            <div className="caseprofiles-score-grid">
              {CONSTITUTION_SCORE_FIELDS.map((item) => {
                const score = watchedValues[item.name];
                return (
                  <div key={item.name} className="caseprofiles-score-card">
                    <div className="caseprofiles-score-card-header">
                      <span>{item.label}</span>
                      <strong>{typeof score === 'number' ? `${score}分` : '--'}</strong>
                    </div>
                    <Progress
                      percent={typeof score === 'number' ? score : 0}
                      size="small"
                      showInfo={false}
                      strokeColor="#285d4c"
                      trailColor="rgba(40, 93, 76, 0.08)"
                    />
                  </div>
                );
              })}
            </div>
          </div>

          <div className="caseprofiles-section-heading">
            <h3>舌诊记录</h3>
            <p>舌诊字段只展示系统回写结果；用户在这里唯一的输入动作是上传 PNG 或 JPG 舌像。</p>
            <div className="caseprofiles-inline-actions">
              <div className="caseprofiles-inline-tags">
                <Tag color={tongueImageUrl ? 'green' : undefined}>{tongueImageUrl ? '舌像已上传' : '待上传舌像'}</Tag>
                {!editingProfile && <Tag>先创建角色后可上传</Tag>}
              </div>
              <Upload
                accept=".png,.jpg,.jpeg"
                showUploadList={false}
                beforeUpload={handleTongueBeforeUpload}
                disabled={!editingProfile || tongueUploading}
              >
                <Button
                  icon={tongueUploading ? <LoadingOutlined /> : <PictureOutlined />}
                  loading={tongueUploading}
                  disabled={!editingProfile}
                >
                  上传舌像 PNG/JPG
                </Button>
              </Upload>
            </div>
          </div>

          <div className="caseprofiles-tongue-panel">
            <div className="caseprofiles-tongue-preview">
              {tongueImageUrl ? (
                <Image
                  src={tongueImageUrl}
                  alt="舌像预览"
                  className="caseprofiles-tongue-image"
                  preview={{ mask: '查看大图' }}
                />
              ) : (
                <div className="caseprofiles-tongue-placeholder">
                  <PictureOutlined />
                  <strong>还没有舌像</strong>
                  <span>支持 PNG、JPG，上传后会回写到当前角色档案。</span>
                </div>
              )}
            </div>

            <div className="caseprofiles-readonly-grid caseprofiles-readonly-grid-2">
              <div className="caseprofiles-summary-card">
                <span>舌诊结果</span>
                <div className="caseprofiles-inline-tags">
                  {tongueSignals.length ? (
                    tongueSignals.map((item) => <Tag key={item}>{item}</Tag>)
                  ) : (
                    <Tag>等待舌诊结果回写</Tag>
                  )}
                </div>
              </div>
              <div className="caseprofiles-summary-card">
                <span>原始描述</span>
                <p>{watchedValues.tongue_raw_description || '上传舌像后，这里会显示原始舌诊描述或后续分析结果。'}</p>
              </div>
            </div>
          </div>

          <div className="caseprofiles-hidden-fields" aria-hidden="true">
            <Form.Item name="constitution_primary" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="constitution_secondary" hidden>
              <Select
                mode="multiple"
                options={CONSTITUTION_SCORE_FIELDS.map((item) => ({ value: item.label, label: item.label }))}
              />
            </Form.Item>
            {CONSTITUTION_SCORE_FIELDS.map((item) => (
              <Form.Item key={`hidden-${item.name}`} name={item.name} hidden>
                <InputNumber />
              </Form.Item>
            ))}
            <Form.Item name="constitution_assessed_at" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="constitution_reassessment_cycle_days" hidden>
              <InputNumber />
            </Form.Item>
            <Form.Item name="tongue_image_url" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="tongue_color" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="tongue_coating" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="tongue_shape" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="tongue_constitution_hint" hidden>
              <Input />
            </Form.Item>
            <Form.Item name="tongue_raw_description" hidden>
              <Input.TextArea />
            </Form.Item>
          </div>

          <div className="caseprofiles-actions">
            <Button type="primary" loading={saving} onClick={handleSubmit}>
              {editingProfile ? '保存角色' : '创建角色'}
            </Button>
          </div>
        </Form>
      </div>
      <ConstitutionQuestionnaireModal
        open={questionnaireOpen}
        onClose={() => setQuestionnaireOpen(false)}
        onApply={handleQuestionnaireApply}
      />
    </Modal>
  );
};

export default CaseProfileManagerModal;

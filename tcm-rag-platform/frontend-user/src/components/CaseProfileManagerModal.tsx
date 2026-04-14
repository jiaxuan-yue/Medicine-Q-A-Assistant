import React, { useEffect } from 'react';
import { Button, Form, Input, InputNumber, Modal, Radio, Select, message } from 'antd';
import { useCaseProfilesStore } from '../stores/caseProfilesStore';
import { getApiErrorMessage } from '../utils/apiError';
import type { CaseProfilePayload } from '../types';
import './CaseProfiles.css';

const TAG_OPTIONS = ['本人', '家人', '儿童', '老人', '慢病随访', '术后调理'];

const CaseProfileManagerModal: React.FC = () => {
  const [form] = Form.useForm<CaseProfilePayload>();
  const {
    profiles,
    managerOpen,
    editingProfile,
    saving,
    createProfile,
    updateProfile,
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
      tags: editingProfile?.tags || [],
    });
  }, [editingProfile, form, managerOpen]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
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
          initialValues={{ tags: [] }}
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

          <div className="caseprofiles-actions">
            <Button type="primary" loading={saving} onClick={handleSubmit}>
              {editingProfile ? '保存角色' : '创建角色'}
            </Button>
          </div>
        </Form>
      </div>
    </Modal>
  );
};

export default CaseProfileManagerModal;

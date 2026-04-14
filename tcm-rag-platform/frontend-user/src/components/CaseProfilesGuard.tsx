import React, { useEffect } from 'react';
import { Spin } from 'antd';
import { useCaseProfilesStore } from '../stores/caseProfilesStore';
import CaseProfileManagerModal from './CaseProfileManagerModal';
import CaseProfilePickerModal from './CaseProfilePickerModal';

const guardStyle: React.CSSProperties = {
  minHeight: '100vh',
  display: 'grid',
  placeItems: 'center',
};

const CaseProfilesGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { checked, loading, loadProfiles } = useCaseProfilesStore();

  useEffect(() => {
    if (!checked) {
      loadProfiles().catch(() => {
        // keep guard minimal; request errors are handled by api layer / UI retry.
      });
    }
  }, [checked, loadProfiles]);

  if (!checked || loading) {
    return (
      <div style={guardStyle}>
        <Spin size="large" tip="正在加载角色档案..." />
      </div>
    );
  }

  return (
    <>
      {children}
      <CaseProfileManagerModal />
      <CaseProfilePickerModal />
    </>
  );
};

export default CaseProfilesGuard;

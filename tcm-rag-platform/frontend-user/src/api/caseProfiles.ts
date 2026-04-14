import client from './client';
import type { ApiResponse, CaseProfile, CaseProfilePayload } from '../types';

export const caseProfilesApi = {
  list: () => client.get<ApiResponse<CaseProfile[]>>('/case-profiles'),
  create: (payload: CaseProfilePayload) =>
    client.post<ApiResponse<CaseProfile>>('/case-profiles', payload),
  update: (profileId: number, payload: CaseProfilePayload) =>
    client.put<ApiResponse<CaseProfile>>(`/case-profiles/${profileId}`, payload),
};

import { create } from 'zustand';
import { caseProfilesApi } from '../api/caseProfiles';
import type { CaseProfile, CaseProfilePayload } from '../types';

interface CaseProfilesState {
  profiles: CaseProfile[];
  activeProfileId: number | null;
  checked: boolean;
  loading: boolean;
  saving: boolean;
  managerOpen: boolean;
  pickerOpen: boolean;
  editingProfile: CaseProfile | null;

  loadProfiles: () => Promise<CaseProfile[]>;
  createProfile: (payload: CaseProfilePayload) => Promise<CaseProfile>;
  updateProfile: (profileId: number, payload: CaseProfilePayload) => Promise<CaseProfile>;
  setActiveProfileId: (profileId: number | null) => void;
  openManager: (profile?: CaseProfile | null) => void;
  closeManager: () => void;
  openPicker: () => void;
  closePicker: () => void;
  reset: () => void;
}

export const useCaseProfilesStore = create<CaseProfilesState>((set, get) => ({
  profiles: [],
  activeProfileId: null,
  checked: false,
  loading: false,
  saving: false,
  managerOpen: false,
  pickerOpen: false,
  editingProfile: null,

  loadProfiles: async () => {
    set({ loading: true });
    try {
      const res = await caseProfilesApi.list();
      const profiles = res.data.data;
      set((state) => ({
        profiles,
        checked: true,
        loading: false,
        managerOpen: profiles.length === 0,
        activeProfileId: state.activeProfileId ?? profiles[0]?.id ?? null,
      }));
      return profiles;
    } catch (error) {
      set({ loading: false, checked: true });
      throw error;
    }
  },

  createProfile: async (payload) => {
    set({ saving: true });
    try {
      const res = await caseProfilesApi.create(payload);
      const profile = res.data.data;
      set((state) => ({
        profiles: [profile, ...state.profiles],
        saving: false,
        managerOpen: false,
        activeProfileId: profile.id,
        editingProfile: null,
      }));
      return profile;
    } catch (error) {
      set({ saving: false });
      throw error;
    }
  },

  updateProfile: async (profileId, payload) => {
    set({ saving: true });
    try {
      const res = await caseProfilesApi.update(profileId, payload);
      const profile = res.data.data;
      set((state) => ({
        profiles: state.profiles.map((item) => (item.id === profile.id ? profile : item)),
        saving: false,
        managerOpen: false,
        editingProfile: null,
      }));
      return profile;
    } catch (error) {
      set({ saving: false });
      throw error;
    }
  },

  setActiveProfileId: (profileId) => set({ activeProfileId: profileId }),

  openManager: (profile = null) => set({ managerOpen: true, editingProfile: profile }),
  closeManager: () => {
    const { profiles } = get();
    if (profiles.length > 0) {
      set({ managerOpen: false, editingProfile: null });
    }
  },

  openPicker: () => set({ pickerOpen: true }),
  closePicker: () => set({ pickerOpen: false }),

  reset: () =>
    set({
      profiles: [],
      activeProfileId: null,
      checked: false,
      loading: false,
      saving: false,
      managerOpen: false,
      pickerOpen: false,
      editingProfile: null,
    }),
}));

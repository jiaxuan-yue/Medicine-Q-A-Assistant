import type { UserLocationPayload } from '../types';

const STORAGE_KEY = 'user_live_location';

function normalizeLocationPayload(raw: unknown): UserLocationPayload | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const candidate = raw as Record<string, unknown>;
  if (typeof candidate.latitude !== 'number' || typeof candidate.longitude !== 'number') {
    return null;
  }
  return {
    latitude: candidate.latitude,
    longitude: candidate.longitude,
    accuracy_m: typeof candidate.accuracy_m === 'number' ? candidate.accuracy_m : undefined,
    source: typeof candidate.source === 'string' ? candidate.source : 'browser-geolocation',
    label: typeof candidate.label === 'string' ? candidate.label : undefined,
    city: typeof candidate.city === 'string' ? candidate.city : undefined,
    province: typeof candidate.province === 'string' ? candidate.province : undefined,
  };
}

export function getCachedUserLocation(): UserLocationPayload | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return normalizeLocationPayload(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function cacheUserLocation(location: UserLocationPayload): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(location));
}

export function clearCachedUserLocation(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

export async function requestBrowserLocation(): Promise<UserLocationPayload> {
  if (!navigator.geolocation) {
    throw new Error('当前浏览器不支持定位');
  }

  return await new Promise<UserLocationPayload>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const payload: UserLocationPayload = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_m: position.coords.accuracy,
          source: 'browser-geolocation',
          label: `纬度 ${position.coords.latitude.toFixed(4)} / 经度 ${position.coords.longitude.toFixed(4)}`,
        };
        cacheUserLocation(payload);
        resolve(payload);
      },
      (error) => {
        reject(new Error(error.message || '定位失败'));
      },
      {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 5 * 60 * 1000,
      },
    );
  });
}

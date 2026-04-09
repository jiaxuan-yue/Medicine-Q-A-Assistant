export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function getToken(): string | null {
  return localStorage.getItem('admin_access_token');
}

export function setToken(token: string): void {
  localStorage.setItem('admin_access_token', token);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem('admin_refresh_token');
}

export function setRefreshToken(token: string): void {
  localStorage.setItem('admin_refresh_token', token);
}

export function clearTokens(): void {
  localStorage.removeItem('admin_access_token');
  localStorage.removeItem('admin_refresh_token');
}

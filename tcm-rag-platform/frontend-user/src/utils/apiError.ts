export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  const err = error as {
    response?: {
      data?: {
        message?: string;
      };
    };
    message?: string;
  };

  return err.response?.data?.message || err.message || fallback;
}


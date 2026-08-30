const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 15000;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const { timeoutMs: _timeoutMs, ...requestOptions } = options;
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestOptions,
      signal: requestOptions.signal || controller.signal,
      headers: { Accept: 'application/json', ...(requestOptions.headers || {}) },
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const detail = typeof payload === 'object' && payload !== null
        ? payload.detail || payload.message || JSON.stringify(payload)
        : payload;
      throw new Error(detail || `Request failed with status ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('Request timed out. Check backend connectivity.');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

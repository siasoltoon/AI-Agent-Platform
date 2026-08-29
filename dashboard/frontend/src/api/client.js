const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
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
}

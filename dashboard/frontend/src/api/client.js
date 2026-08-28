const API_BASE_URL = 'http://localhost:8000';

export async function apiRequest(path, options = {}) {
  return fetch(`${API_BASE_URL}${path}`, options);
}

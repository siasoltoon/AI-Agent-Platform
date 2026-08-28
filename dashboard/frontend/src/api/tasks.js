import { apiRequest } from './client';

export async function getTasks() {
  return apiRequest('/tasks/');
}

export async function createTask(payload) {
  return apiRequest('/tasks/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

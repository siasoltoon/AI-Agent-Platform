import { apiRequest } from './client';

export async function getDashboardSummary() {
  return apiRequest('/dashboard/summary');
}

export async function getDiagnostics() {
  return apiRequest('/dashboard/diagnostics');
}

export async function getTaskEvents(taskId) {
  return apiRequest(`/tasks/${encodeURIComponent(taskId)}/events`);
}

export async function cancelTask(taskId) {
  return apiRequest(`/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
}

export async function retryTask(taskId) {
  return apiRequest(`/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' });
}

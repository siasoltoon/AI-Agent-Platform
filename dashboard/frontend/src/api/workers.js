import { apiRequest } from './client';

export async function getWorkers() {
  return apiRequest('/workers/');
}

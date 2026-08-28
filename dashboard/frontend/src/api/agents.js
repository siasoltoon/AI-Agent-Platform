import { apiRequest } from './client';

export async function getAgents() {
  return apiRequest('/agents/');
}

// API client for the observability backend

import type { EventResponse, MetricsResponse, SessionDetail, SessionSummary } from './types'

const API_BASE = '/api'

async function fetchJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

export const api = {
  // Health check
  health: () => fetchJSON<{ status: string; service: string }>('/health'),

  // Events
  getEvents: (params?: { session_id?: string; limit?: number; offset?: number }) => {
    const searchParams = new URLSearchParams()
    if (params?.session_id) searchParams.set('session_id', params.session_id)
    if (params?.limit) searchParams.set('limit', params.limit.toString())
    if (params?.offset) searchParams.set('offset', params.offset.toString())
    const query = searchParams.toString()
    return fetchJSON<EventResponse[]>(`/events${query ? `?${query}` : ''}`)
  },

  // Sessions
  getSessions: (limit?: number) => {
    const query = limit ? `?limit=${limit}` : ''
    return fetchJSON<SessionSummary[]>(`/sessions${query}`)
  },

  getSession: (sessionId: string) => {
    return fetchJSON<SessionDetail>(`/sessions/${sessionId}`)
  },

  // Metrics
  getMetrics: () => fetchJSON<MetricsResponse>('/metrics'),

  // Manual import trigger
  triggerImport: () =>
    fetch(`${API_BASE}/import`, { method: 'POST' }).then((r) => r.json()) as Promise<{ imported: number }>,
}


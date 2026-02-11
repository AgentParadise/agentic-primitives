// React Query hooks for API data

import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useMetrics() {
  return useQuery({
    queryKey: ['metrics'],
    queryFn: api.getMetrics,
  })
}

export function useEvents(params?: { session_id?: string; limit?: number }) {
  return useQuery({
    queryKey: ['events', params],
    queryFn: () => api.getEvents(params),
  })
}

export function useSessions(limit?: number) {
  return useQuery({
    queryKey: ['sessions', limit],
    queryFn: () => api.getSessions(limit),
  })
}

export function useSession(sessionId: string) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.getSession(sessionId),
    enabled: !!sessionId,
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 10000,
  })
}


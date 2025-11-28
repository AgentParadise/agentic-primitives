// API response types matching backend schemas

export interface EventResponse {
  id: string
  timestamp: string
  event_type: string
  handler: string
  hook_event: string | null
  tool_name: string | null
  session_id: string | null
  decision: string | null
  reason: string | null
  success: boolean | null
  estimated_tokens: number | null
  estimated_cost_usd: number | null
  input_preview: string | null  // File path, command, etc.
}

export interface SessionSummary {
  session_id: string
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  model: string | null
  total_events: number
  tool_calls: number
  blocked_calls: number
  total_tokens: number
  total_cost_usd: number
}

export interface SessionDetail extends SessionSummary {
  events: EventResponse[]
  tools_used: Record<string, number>
}

export interface MetricsResponse {
  total_sessions: number
  total_events: number
  total_tool_calls: number
  total_blocked: number
  total_tokens: number
  total_cost_usd: number
  tokens_last_hour: number
  tokens_last_24h: number
  cost_last_hour: number
  cost_last_24h: number
  calls_by_tool: Record<string, number>
  blocks_by_tool: Record<string, number>
  tokens_by_model: Record<string, number>
  cost_by_model: Record<string, number>
}


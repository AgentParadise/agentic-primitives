import { Clock, Hash, Zap } from 'lucide-react'
import { useSessions } from '../hooks/useApi'
import type { SessionSummary } from '../api/types'

export default function Sessions() {
  const { data: sessions, isLoading } = useSessions(50)

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Sessions</h1>
        <p className="text-gray-500 text-sm mt-1">Browse agent session history</p>
      </div>

      {/* Sessions List */}
      <div className="panel overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading sessions...</div>
        ) : sessions?.length === 0 ? (
          <div className="p-8 text-center text-gray-500">No sessions yet</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-panel-border text-left text-xs uppercase tracking-wider text-gray-500">
                <th className="p-4 font-medium">Session</th>
                <th className="p-4 font-medium">Started</th>
                <th className="p-4 font-medium">Duration</th>
                <th className="p-4 font-medium">Events</th>
                <th className="p-4 font-medium">Tools</th>
                <th className="p-4 font-medium">Tokens</th>
                <th className="p-4 font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-panel-border">
              {sessions?.map((session) => (
                <SessionRow key={session.session_id} session={session} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function SessionRow({ session }: { session: SessionSummary }) {
  const shortId = session.session_id.slice(0, 8)
  const startedAt = new Date(session.started_at)
  const duration = session.duration_seconds
    ? formatDuration(session.duration_seconds)
    : 'In progress'

  return (
    <tr className="hover:bg-void-800/50 transition-colors">
      <td className="p-4">
        <a
          href={`/sessions/${session.session_id}`}
          className="flex items-center gap-2 text-signal-cyan hover:underline font-mono text-sm"
        >
          <Hash size={14} />
          {shortId}
        </a>
      </td>
      <td className="p-4 text-sm text-gray-400">
        {startedAt.toLocaleString()}
      </td>
      <td className="p-4">
        <span className="flex items-center gap-1 text-sm text-gray-400">
          <Clock size={14} />
          {duration}
        </span>
      </td>
      <td className="p-4 font-mono text-sm">{session.total_events}</td>
      <td className="p-4">
        <span className="flex items-center gap-1 text-sm">
          <Zap size={14} className="text-signal-emerald" />
          {session.tool_calls}
          {session.blocked_calls > 0 && (
            <span className="text-signal-rose ml-1">({session.blocked_calls} blocked)</span>
          )}
        </span>
      </td>
      <td className="p-4 font-mono text-sm">{session.total_tokens.toLocaleString()}</td>
      <td className="p-4 font-mono text-sm text-signal-amber">
        {formatCost(session.total_cost_usd)}
      </td>
    </tr>
  )
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  return `${(seconds / 3600).toFixed(1)}h`
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0.00'
  if (cost > 0 && cost < 0.01) return '<$0.01'
  return `$${cost.toFixed(4)}`
}


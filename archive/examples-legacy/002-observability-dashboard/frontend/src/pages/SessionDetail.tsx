import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, Hash, Zap, DollarSign, Activity } from 'lucide-react'
import { useSession } from '../hooks/useApi'
import EventFeed from '../components/EventFeed'

export default function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const { data: session, isLoading, error } = useSession(sessionId ?? '')

  if (isLoading) {
    return (
      <div className="p-8 text-center text-gray-500">Loading session...</div>
    )
  }

  if (error || !session) {
    return (
      <div className="p-8">
        <Link to="/sessions" className="flex items-center gap-2 text-signal-cyan hover:underline mb-4">
          <ArrowLeft size={16} />
          Back to Sessions
        </Link>
        <div className="text-signal-rose">Session not found</div>
      </div>
    )
  }

  const startedAt = new Date(session.started_at)
  const duration = session.duration_seconds
    ? formatDuration(session.duration_seconds)
    : 'In progress'

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <Link to="/sessions" className="flex items-center gap-2 text-signal-cyan hover:underline mb-4 text-sm">
          <ArrowLeft size={16} />
          Back to Sessions
        </Link>
        <div className="flex items-center gap-3">
          <Hash className="text-gray-500" size={24} />
          <div>
            <h1 className="text-2xl font-semibold font-mono">{session.session_id.slice(0, 12)}...</h1>
            <p className="text-gray-500 text-sm mt-1">Started {startedAt.toLocaleString()}</p>
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={<Clock size={18} />} label="Duration" value={duration} />
        <StatCard icon={<Activity size={18} />} label="Events" value={session.total_events.toString()} />
        <StatCard
          icon={<Zap size={18} />}
          label="Tool Calls"
          value={`${session.tool_calls} (${session.blocked_calls} blocked)`}
        />
        <StatCard
          icon={<DollarSign size={18} />}
          label="Cost"
          value={formatCost(session.total_cost_usd)}
        />
      </div>

      {/* Tools Used */}
      {Object.keys(session.tools_used).length > 0 && (
        <div className="panel p-6">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Tools Used</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(session.tools_used).map(([tool, count]) => (
              <span
                key={tool}
                className="px-3 py-1 bg-void-800 rounded-full text-sm font-mono"
              >
                {tool}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Event Timeline */}
      <div className="panel p-6">
        <h3 className="text-sm font-medium text-gray-400 mb-4">Event Timeline</h3>
        <EventFeed events={session.events} loading={false} />
      </div>
    </div>
  )
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2 text-gray-500 mb-1">
        {icon}
        <span className="text-xs uppercase tracking-wider">{label}</span>
      </div>
      <div className="font-mono text-lg">{value}</div>
    </div>
  )
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`
}

function formatCost(cost: number): string {
  if (cost === 0) return '$0.00'
  if (cost > 0 && cost < 0.01) return '<$0.01'
  return `$${cost.toFixed(4)}`
}


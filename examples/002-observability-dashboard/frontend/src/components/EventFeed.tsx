import { CheckCircle, XCircle, AlertTriangle, Terminal, FileText, MessageSquare } from 'lucide-react'
import type { EventResponse } from '../api/types'

interface EventFeedProps {
  events: EventResponse[]
  loading?: boolean
}

export default function EventFeed({ events, loading }: EventFeedProps) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-16 bg-void-800 rounded-lg animate-pulse" />
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">
        No events yet. Events will appear here as your agent runs.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {events.map((event) => (
        <EventRow key={event.id} event={event} />
      ))}
    </div>
  )
}

function EventRow({ event }: { event: EventResponse }) {
  const timestamp = new Date(event.timestamp)
  const timeStr = timestamp.toLocaleTimeString()

  const { icon, color, label } = getEventStyle(event)

  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-void-800/50 hover:bg-void-800 transition-colors">
      <div className={`mt-0.5 ${color}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">{label}</span>
          {event.tool_name && (
            <code className="text-xs bg-void-900 px-2 py-0.5 rounded font-mono">
              {event.tool_name}
            </code>
          )}
        </div>
        {event.reason && (
          <p className="text-xs text-gray-500 mt-1 truncate">{event.reason}</p>
        )}
      </div>
      <div className="text-xs text-gray-600 font-mono whitespace-nowrap">{timeStr}</div>
    </div>
  )
}

function getEventStyle(event: EventResponse): {
  icon: React.ReactNode
  color: string
  label: string
} {
  // Block decision
  if (event.decision === 'block') {
    return {
      icon: <XCircle size={18} />,
      color: 'text-signal-rose',
      label: 'Blocked',
    }
  }

  // Tool execution
  if (event.event_type === 'tool_execution') {
    if (event.success === false) {
      return {
        icon: <AlertTriangle size={18} />,
        color: 'text-signal-amber',
        label: 'Tool Error',
      }
    }
    return {
      icon: <CheckCircle size={18} />,
      color: 'text-signal-emerald',
      label: 'Tool Executed',
    }
  }

  // Hook decision (allow)
  if (event.event_type === 'hook_decision') {
    const toolIcon = getToolIcon(event.tool_name)
    return {
      icon: toolIcon,
      color: 'text-signal-cyan',
      label: 'Tool Approved',
    }
  }

  // User prompt
  if (event.handler === 'user-prompt') {
    return {
      icon: <MessageSquare size={18} />,
      color: 'text-signal-violet',
      label: 'User Prompt',
    }
  }

  // Default
  return {
    icon: <CheckCircle size={18} />,
    color: 'text-gray-500',
    label: event.event_type,
  }
}

function getToolIcon(toolName: string | null): React.ReactNode {
  switch (toolName) {
    case 'Bash':
      return <Terminal size={18} />
    case 'Write':
    case 'Read':
    case 'Edit':
      return <FileText size={18} />
    default:
      return <CheckCircle size={18} />
  }
}


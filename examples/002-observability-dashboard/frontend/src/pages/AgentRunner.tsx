import { useState, useEffect, useRef } from 'react'
import { Play, Loader2, CheckCircle, XCircle, Terminal, FileText, Zap } from 'lucide-react'
import { api } from '../api/client'
import type { EventResponse } from '../api/types'

interface AgentModel {
  id: string
  name: string
  description: string
}

type AgentStatus = 'idle' | 'running' | 'completed' | 'failed'

export default function AgentRunner() {
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('claude-haiku-4-5-20251001')
  const [models, setModels] = useState<AgentModel[]>([])
  const [status, setStatus] = useState<AgentStatus>('idle')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [events, setEvents] = useState<EventResponse[]>([])
  const [error, setError] = useState<string | null>(null)
  const eventsEndRef = useRef<HTMLDivElement>(null)

  // Load available models
  useEffect(() => {
    fetch('/api/agent/models')
      .then(res => res.json())
      .then(data => setModels(data.models))
      .catch(() => {
        // Default models if API fails
        setModels([
          { id: 'claude-haiku-4-5-20251001', name: 'Claude Haiku 4.5', description: 'Fast & cheap' },
          { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', description: 'Balanced' },
        ])
      })
  }, [])

  // Poll for events when running
  useEffect(() => {
    if (status !== 'running' || !sessionId) return

    const pollEvents = async () => {
      try {
        const sessionEvents = await api.getSessionEvents(sessionId)
        setEvents(sessionEvents.reverse()) // Show newest at bottom

        // Check if session completed
        const statusRes = await fetch(`/api/agent/status/${sessionId}`)
        const statusData = await statusRes.json()

        if (statusData.status === 'completed') {
          setStatus('completed')
        } else if (statusData.status === 'failed') {
          setStatus('failed')
          setError(statusData.error || 'Agent task failed')
        }
      } catch (e) {
        // Ignore poll errors
      }
    }

    const interval = setInterval(pollEvents, 1000)
    pollEvents() // Initial poll

    return () => clearInterval(interval)
  }, [status, sessionId])

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const handleRun = async () => {
    if (!prompt.trim()) return

    setStatus('running')
    setError(null)
    setEvents([])

    try {
      const res = await fetch('/api/agent/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model }),
      })

      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.detail || 'Failed to start agent')
      }

      const data = await res.json()
      setSessionId(data.session_id)
    } catch (e) {
      setStatus('failed')
      setError(e instanceof Error ? e.message : 'Failed to start agent')
    }
  }

  const handleReset = () => {
    setStatus('idle')
    setSessionId(null)
    setEvents([])
    setError(null)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-gradient-to-br from-signal-violet/20 to-signal-cyan/20">
          <Zap className="w-6 h-6 text-signal-violet" />
        </div>
        <div>
          <h1 className="text-2xl font-bold">Agent Runner</h1>
          <p className="text-sm text-gray-500">Run ad-hoc agent tasks and watch them execute</p>
        </div>
      </div>

      {/* Task Input */}
      <div className="bg-void-900 rounded-xl p-6 border border-void-800">
        <div className="space-y-4">
          {/* Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Task Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe what you want the agent to do..."
              className="w-full h-32 px-4 py-3 rounded-lg bg-void-950 border border-void-700 
                         text-gray-100 placeholder-gray-600 resize-none
                         focus:outline-none focus:ring-2 focus:ring-signal-cyan/50 focus:border-signal-cyan"
              disabled={status === 'running'}
            />
          </div>

          {/* Model Selection */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-400 mb-2">Model</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full px-4 py-2 rounded-lg bg-void-950 border border-void-700 
                           text-gray-100 focus:outline-none focus:ring-2 focus:ring-signal-cyan/50"
                disabled={status === 'running'}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} - {m.description}
                  </option>
                ))}
              </select>
            </div>

            {/* Run Button */}
            <div className="pt-6">
              {status === 'idle' ? (
                <button
                  onClick={handleRun}
                  disabled={!prompt.trim()}
                  className="flex items-center gap-2 px-6 py-2 rounded-lg font-medium
                             bg-gradient-to-r from-signal-cyan to-signal-violet
                             hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed
                             transition-opacity"
                >
                  <Play size={18} />
                  Run Agent
                </button>
              ) : status === 'running' ? (
                <button
                  disabled
                  className="flex items-center gap-2 px-6 py-2 rounded-lg font-medium
                             bg-signal-amber/20 text-signal-amber cursor-wait"
                >
                  <Loader2 size={18} className="animate-spin" />
                  Running...
                </button>
              ) : (
                <button
                  onClick={handleReset}
                  className="flex items-center gap-2 px-6 py-2 rounded-lg font-medium
                             bg-void-800 hover:bg-void-700 transition-colors"
                >
                  Run Another
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Progress & Events */}
      {(status !== 'idle' || events.length > 0) && (
        <div className="bg-void-900 rounded-xl border border-void-800 overflow-hidden">
          {/* Status Header */}
          <div className="px-6 py-4 border-b border-void-800 flex items-center justify-between">
            <div className="flex items-center gap-3">
              {status === 'running' && (
                <>
                  <Loader2 className="w-5 h-5 text-signal-amber animate-spin" />
                  <span className="font-medium text-signal-amber">Agent Running</span>
                </>
              )}
              {status === 'completed' && (
                <>
                  <CheckCircle className="w-5 h-5 text-signal-emerald" />
                  <span className="font-medium text-signal-emerald">Completed</span>
                </>
              )}
              {status === 'failed' && (
                <>
                  <XCircle className="w-5 h-5 text-signal-rose" />
                  <span className="font-medium text-signal-rose">Failed</span>
                </>
              )}
            </div>

            {sessionId && (
              <span className="text-xs text-gray-500 font-mono">
                Session: {sessionId.slice(0, 8)}...
              </span>
            )}
          </div>

          {/* Progress Bar */}
          {status === 'running' && (
            <div className="h-1 bg-void-800">
              <div className="h-full bg-gradient-to-r from-signal-cyan to-signal-violet animate-pulse w-full" />
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="px-6 py-3 bg-signal-rose/10 border-b border-signal-rose/20">
              <p className="text-sm text-signal-rose">{error}</p>
            </div>
          )}

          {/* Events Feed */}
          <div className="max-h-96 overflow-y-auto p-4 space-y-2">
            {events.length === 0 && status === 'running' && (
              <div className="text-center text-gray-500 py-8">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-50" />
                <p>Waiting for events...</p>
              </div>
            )}

            {events.map((event) => (
              <EventItem key={event.id} event={event} />
            ))}

            <div ref={eventsEndRef} />
          </div>

          {/* Summary */}
          {status === 'completed' && events.length > 0 && (
            <div className="px-6 py-4 border-t border-void-800 bg-void-950/50">
              <div className="flex items-center gap-6 text-sm">
                <span className="text-gray-400">
                  <strong className="text-gray-200">{events.length}</strong> events
                </span>
                <span className="text-gray-400">
                  <strong className="text-gray-200">
                    {events.filter(e => e.tool_name).length}
                  </strong> tool calls
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Quick Examples */}
      {status === 'idle' && (
        <div className="bg-void-900/50 rounded-xl p-6 border border-void-800/50">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Quick Examples</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {[
              'Create a hello.py file that prints "Hello from the agent!"',
              'List the current directory and show me what files are here',
              'Write a simple bash script that shows system info',
              'Create a TODO.md with 3 sample tasks',
            ].map((example) => (
              <button
                key={example}
                onClick={() => setPrompt(example)}
                className="text-left px-4 py-2 rounded-lg bg-void-800/50 hover:bg-void-800 
                           text-sm text-gray-400 hover:text-gray-200 transition-colors truncate"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EventItem({ event }: { event: EventResponse }) {
  const getIcon = () => {
    if (event.tool_name === 'Bash') return <Terminal size={16} />
    if (event.tool_name === 'Write' || event.tool_name === 'Read') return <FileText size={16} />
    if (event.decision === 'block') return <XCircle size={16} />
    return <CheckCircle size={16} />
  }

  const getColor = () => {
    if (event.decision === 'block') return 'text-signal-rose'
    if (event.event_type.includes('session_end')) return 'text-gray-400'
    if (event.event_type.includes('session_start')) return 'text-signal-emerald'
    if (event.tool_name) return 'text-signal-cyan'
    return 'text-gray-500'
  }

  const getLabel = () => {
    if (event.event_type === 'agent_session_start') return 'Session Started'
    if (event.event_type === 'agent_session_end') return 'Session Ended'
    if (event.event_type === 'tool_call') return `Tool: ${event.tool_name}`
    if (event.event_type === 'PreToolUse') return `Approved: ${event.tool_name}`
    if (event.event_type === 'PostToolUse') return `Executed: ${event.tool_name}`
    return event.event_type
  }

  return (
    <div className="flex items-start gap-3 p-2 rounded-lg bg-void-800/30 hover:bg-void-800/50 transition-colors">
      <div className={`mt-0.5 ${getColor()}`}>{getIcon()}</div>
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium">{getLabel()}</span>
        {event.input_preview && (
          <p className="text-xs text-signal-cyan/70 font-mono truncate mt-0.5">
            {event.input_preview}
          </p>
        )}
      </div>
      <span className="text-xs text-gray-600 font-mono">
        {new Date(event.timestamp).toLocaleTimeString()}
      </span>
    </div>
  )
}


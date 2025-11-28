import { Activity, DollarSign, Shield, Zap } from 'lucide-react'
import { useMetrics, useEvents } from '../hooks/useApi'
import MetricCard from '../components/MetricCard'
import EventFeed from '../components/EventFeed'
import TokenChart from '../components/TokenChart'
import ToolBreakdown from '../components/ToolBreakdown'

export default function Dashboard() {
  const { data: metrics, isLoading: metricsLoading } = useMetrics()
  const { data: events, isLoading: eventsLoading } = useEvents({ limit: 20 })

  return (
    <div className="p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-gray-500 text-sm mt-1">Real-time agent activity and metrics</p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Events"
          value={metrics?.total_events ?? 0}
          icon={<Activity className="text-signal-cyan" size={20} />}
          trend={`${metrics?.tokens_last_hour ?? 0} tokens/hr`}
          glowColor="cyan"
          loading={metricsLoading}
        />
        <MetricCard
          label="Tool Calls"
          value={metrics?.total_tool_calls ?? 0}
          icon={<Zap className="text-signal-emerald" size={20} />}
          trend={`${metrics?.total_blocked ?? 0} blocked`}
          glowColor="emerald"
          loading={metricsLoading}
        />
        <MetricCard
          label="Total Tokens"
          value={formatNumber(metrics?.total_tokens ?? 0)}
          icon={<Activity className="text-signal-amber" size={20} />}
          trend={`${formatNumber(metrics?.tokens_last_24h ?? 0)} last 24h`}
          glowColor="amber"
          loading={metricsLoading}
        />
        <MetricCard
          label="Total Cost"
          value={`$${(metrics?.total_cost_usd ?? 0).toFixed(2)}`}
          icon={<DollarSign className="text-signal-violet" size={20} />}
          trend={`$${(metrics?.cost_last_24h ?? 0).toFixed(2)} last 24h`}
          glowColor="violet"
          loading={metricsLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="panel p-6">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Token Usage</h3>
          <TokenChart />
        </div>
        <div className="panel p-6">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Tool Breakdown</h3>
          <ToolBreakdown data={metrics?.calls_by_tool ?? {}} blocks={metrics?.blocks_by_tool ?? {}} />
        </div>
      </div>

      {/* Event Feed */}
      <div className="panel p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-400">Recent Events</h3>
          <span className="text-xs text-gray-600">Auto-refreshing</span>
        </div>
        <EventFeed events={events ?? []} loading={eventsLoading} />
      </div>
    </div>
  )
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}


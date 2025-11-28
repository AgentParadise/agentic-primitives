import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  value: string | number
  icon: ReactNode
  trend?: string
  glowColor?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'violet'
  loading?: boolean
}

export default function MetricCard({
  label,
  value,
  icon,
  trend,
  glowColor = 'cyan',
  loading = false,
}: MetricCardProps) {
  const glowClass = {
    cyan: 'glow-cyan border-signal-cyan/20',
    emerald: 'glow-emerald border-signal-emerald/20',
    amber: 'glow-amber border-signal-amber/20',
    rose: 'glow-rose border-signal-rose/20',
    violet: 'border-signal-violet/20',
  }[glowColor]

  return (
    <div className={`panel p-5 ${glowClass}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="stat-label">{label}</span>
        {icon}
      </div>
      <div className="metric-value">
        {loading ? (
          <div className="h-8 w-24 bg-void-800 rounded animate-pulse" />
        ) : (
          value
        )}
      </div>
      {trend && (
        <div className="text-xs text-gray-500 mt-2">{trend}</div>
      )}
    </div>
  )
}


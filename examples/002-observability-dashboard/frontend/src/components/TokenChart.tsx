import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

// Placeholder data - will be replaced with real time series from API
const mockData = [
  { time: '00:00', tokens: 0 },
  { time: '04:00', tokens: 1200 },
  { time: '08:00', tokens: 3400 },
  { time: '12:00', tokens: 5600 },
  { time: '16:00', tokens: 8900 },
  { time: '20:00', tokens: 12400 },
  { time: '24:00', tokens: 15000 },
]

export default function TokenChart() {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={mockData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#6b7280', fontSize: 12 }}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            tickFormatter={(v) => (v >= 1000 ? `${v / 1000}K` : v)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid rgba(75, 85, 99, 0.4)',
              borderRadius: '8px',
              color: '#f3f4f6',
            }}
            formatter={(value: number) => [`${value.toLocaleString()} tokens`, 'Usage']}
          />
          <Area
            type="monotone"
            dataKey="tokens"
            stroke="#22d3ee"
            strokeWidth={2}
            fill="url(#tokenGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}


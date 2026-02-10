import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface ToolBreakdownProps {
  data: Record<string, number>
  blocks: Record<string, number>
}

export default function ToolBreakdown({ data, blocks }: ToolBreakdownProps) {
  // Transform data for chart
  const chartData = Object.entries(data).map(([name, calls]) => ({
    name,
    calls,
    blocked: blocks[name] ?? 0,
  }))

  // Sort by calls descending
  chartData.sort((a, b) => b.calls - a.calls)

  if (chartData.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-gray-500">
        No tool usage data yet
      </div>
    )
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 10, left: 60, bottom: 0 }}>
          <XAxis
            type="number"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#6b7280', fontSize: 12 }}
          />
          <YAxis
            type="category"
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fill: '#6b7280', fontSize: 12 }}
            width={60}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid rgba(75, 85, 99, 0.4)',
              borderRadius: '8px',
              color: '#f3f4f6',
            }}
            formatter={(value: number, name: string) => [
              value,
              name === 'calls' ? 'Total Calls' : 'Blocked',
            ]}
          />
          <Bar dataKey="calls" stackId="a" radius={[0, 4, 4, 0]}>
            {chartData.map((_, index) => (
              <Cell key={index} fill="#10b981" />
            ))}
          </Bar>
          <Bar dataKey="blocked" stackId="a" radius={[0, 4, 4, 0]}>
            {chartData.map((_, index) => (
              <Cell key={index} fill="#f43f5e" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}


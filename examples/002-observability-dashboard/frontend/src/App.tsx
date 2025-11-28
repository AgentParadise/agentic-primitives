import { Routes, Route } from 'react-router-dom'
import { LayoutDashboard, List, Zap } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Sessions from './pages/Sessions'
import SessionDetail from './pages/SessionDetail'
import AgentRunner from './pages/AgentRunner'
import { useHealth } from './hooks/useApi'

function Sidebar() {
  return (
    <aside className="w-64 bg-void-900 border-r border-panel-border flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-panel-border">
        <h1 className="text-xl font-semibold text-gradient">Agent Observatory</h1>
        <p className="text-xs text-gray-500 mt-1">Claude Agent SDK Observability</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        <NavLink href="/" icon={<LayoutDashboard size={18} />} label="Dashboard" />
        <NavLink href="/sessions" icon={<List size={18} />} label="Sessions" />
        <NavLink href="/run" icon={<Zap size={18} />} label="Run Agent" />
      </nav>

      {/* Status */}
      <StatusIndicator />
    </aside>
  )
}

function NavLink({ href, icon, label }: { href: string; icon: React.ReactNode; label: string }) {
  const isActive = location.pathname === href
  return (
    <a
      href={href}
      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
        isActive
          ? 'bg-signal-cyan/10 text-signal-cyan'
          : 'text-gray-400 hover:text-gray-100 hover:bg-void-800'
      }`}
    >
      {icon}
      {label}
    </a>
  )
}

function StatusIndicator() {
  const { data, isError } = useHealth()
  const isHealthy = data?.status === 'healthy'

  return (
    <div className="p-4 border-t border-panel-border">
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${
            isError ? 'bg-signal-rose' : isHealthy ? 'bg-signal-emerald animate-pulse-slow' : 'bg-signal-amber'
          }`}
        />
        <span className="text-xs text-gray-500">
          {isError ? 'Disconnected' : isHealthy ? 'Connected' : 'Connecting...'}
        </span>
      </div>
    </div>
  )
}

function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto bg-void-950">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:sessionId" element={<SessionDetail />} />
          <Route path="/run" element={<AgentRunner />} />
        </Routes>
      </main>
    </div>
  )
}

export default App


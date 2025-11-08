import { BrowserRouter, Routes, Route, Link, Navigate } from 'react-router-dom'
import { Settings, GitBranch, Users, Activity, History, Loader2 } from 'lucide-react'
import { useAuth } from './hooks/useAuth'
import { ErrorBoundary } from './components/ErrorBoundary'
import { SystemStatusHeader } from './components/system-status'
import DashboardPage from './pages/DashboardPage'
import ProjectConfigPage from './pages/ProjectConfigPage'
import WorkflowConfigPage from './pages/WorkflowConfigPage'
import AgentConfigPage from './pages/AgentConfigPage'
import ConfigHistoryPage from './pages/ConfigHistoryPage'
import AuthRequiredPage from './pages/AuthRequiredPage'

function App() {
  const { isAuthenticated, isLoading } = useAuth()

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Show auth required page if not authenticated
  if (!isAuthenticated) {
    return <AuthRequiredPage />
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <nav className="border-b">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold">Codetoreum</h1>
              <div className="flex space-x-4">
                <Link
                  to="/"
                  className="flex items-center space-x-2 px-3 py-2 rounded-md hover:bg-accent"
                >
                  <Activity className="h-4 w-4" />
                  <span>Dashboard</span>
                </Link>
                <Link
                  to="/config"
                  className="flex items-center space-x-2 px-3 py-2 rounded-md hover:bg-accent"
                >
                  <Settings className="h-4 w-4" />
                  <span>Project</span>
                </Link>
                <Link
                  to="/workflows"
                  className="flex items-center space-x-2 px-3 py-2 rounded-md hover:bg-accent"
                >
                  <GitBranch className="h-4 w-4" />
                  <span>Workflows</span>
                </Link>
                <Link
                  to="/agents"
                  className="flex items-center space-x-2 px-3 py-2 rounded-md hover:bg-accent"
                >
                  <Users className="h-4 w-4" />
                  <span>Agents</span>
                </Link>
                <Link
                  to="/history"
                  className="flex items-center space-x-2 px-3 py-2 rounded-md hover:bg-accent"
                >
                  <History className="h-4 w-4" />
                  <span>History</span>
                </Link>
              </div>
            </div>
          </div>
        </nav>

        <main className="container mx-auto px-4 py-8">
          {/* System Status Header */}
          <div className="mb-6">
            <SystemStatusHeader />
          </div>

          <Routes>
            <Route
              path="/"
              element={
                <ErrorBoundary>
                  <DashboardPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="/config"
              element={
                <ErrorBoundary>
                  <ProjectConfigPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="/workflows"
              element={
                <ErrorBoundary>
                  <WorkflowConfigPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="/agents"
              element={
                <ErrorBoundary>
                  <AgentConfigPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="/history"
              element={
                <ErrorBoundary>
                  <ConfigHistoryPage />
                </ErrorBoundary>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App

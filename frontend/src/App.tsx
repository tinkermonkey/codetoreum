import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from './hooks/useAuth'
import { ErrorBoundary } from './components/ErrorBoundary'
import { SystemStatusHeader } from './components/system-status'
import { AppNav } from './components/layout/AppNav'
import DashboardPage from './pages/DashboardPage'
import ProjectConfigPage from './pages/ProjectConfigPage'
import WorkflowConfigPage from './pages/WorkflowConfigPage'
import AgentConfigPage from './pages/AgentConfigPage'
import ConfigHistoryPage from './pages/ConfigHistoryPage'
import AuthRequiredPage from './pages/AuthRequiredPage'
import { PipelineRunDetailsPage } from './pages/PipelineRunDetailsPage'
import { PipelineFlowPage } from './pages/PipelineFlowPage'

function App() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" role="status" aria-live="polite">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-7 w-7 animate-spin text-primary" aria-hidden />
          <p className="text-sm text-muted-foreground">Checking authentication…</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <AuthRequiredPage />
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/workflows/runs/:id?"
          element={
            <ErrorBoundary>
              <PipelineRunDetailsPage />
            </ErrorBoundary>
          }
        />
        <Route
          path="/workflows/flow/:id?"
          element={
            <ErrorBoundary>
              <PipelineFlowPage />
            </ErrorBoundary>
          }
        />

        <Route
          path="*"
          element={
            <div className="min-h-screen bg-background">
              <AppNav />
              <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
                <div className="mb-8">
                  <SystemStatusHeader />
                </div>
                <Routes>
                  <Route path="/" element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
                  <Route path="/config" element={<ErrorBoundary><ProjectConfigPage /></ErrorBoundary>} />
                  <Route path="/workflows" element={<ErrorBoundary><WorkflowConfigPage /></ErrorBoundary>} />
                  <Route path="/agents" element={<ErrorBoundary><AgentConfigPage /></ErrorBoundary>} />
                  <Route path="/history" element={<ErrorBoundary><ConfigHistoryPage /></ErrorBoundary>} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </main>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App

import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { Settings, GitBranch, Users } from 'lucide-react'
import ProjectConfigPage from './pages/ProjectConfigPage'
import WorkflowConfigPage from './pages/WorkflowConfigPage'
import AgentConfigPage from './pages/AgentConfigPage'
import ConfigHistoryPage from './pages/ConfigHistoryPage'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-background">
        <nav className="border-b">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold">Codetoreum Configuration</h1>
              <div className="flex space-x-4">
                <Link
                  to="/"
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
                  <span>History</span>
                </Link>
              </div>
            </div>
          </div>
        </nav>

        <main className="container mx-auto px-4 py-8">
          <Routes>
            <Route path="/" element={<ProjectConfigPage />} />
            <Route path="/workflows" element={<WorkflowConfigPage />} />
            <Route path="/agents" element={<AgentConfigPage />} />
            <Route path="/history" element={<ConfigHistoryPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App

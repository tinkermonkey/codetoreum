import { AlertCircle, Terminal } from 'lucide-react'
import { Card } from '../components/ui/card'

export default function AuthRequiredPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="max-w-2xl w-full p-8 space-y-6">
        <div className="flex items-center space-x-3">
          <AlertCircle className="h-8 w-8 text-yellow-500" />
          <h1 className="text-2xl font-bold">Authentication Required</h1>
        </div>

        <div className="space-y-4 text-muted-foreground">
          <p>
            To access the Codetoreum dashboard, you need an authentication token.
          </p>

          <div className="bg-muted p-4 rounded-md space-y-3">
            <div className="flex items-start space-x-2">
              <Terminal className="h-5 w-5 mt-0.5 text-primary" />
              <div>
                <p className="font-semibold text-foreground mb-2">
                  How to get your authentication token:
                </p>
                <ol className="list-decimal list-inside space-y-2 text-sm">
                  <li>Start the Codetoreum API server</li>
                  <li>Look for the authentication URL in the server logs</li>
                  <li>Click the URL or copy it to your browser</li>
                  <li>You'll be automatically authenticated and redirected to the dashboard</li>
                </ol>
              </div>
            </div>
          </div>

          <div className="bg-muted p-4 rounded-md space-y-2">
            <p className="font-semibold text-foreground">Example server output:</p>
            <pre className="text-xs bg-background p-3 rounded overflow-x-auto">
{`============================================================
Codetoreum API Server
============================================================

Server URL: http://localhost:8000

Authentication token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

Access URL: http://localhost:8000/?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

For API access, use one of:
  - Query parameter: ?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
  - Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

============================================================`}
            </pre>
          </div>

          <div className="border-l-4 border-yellow-500 bg-yellow-50 dark:bg-yellow-900/10 p-4 rounded">
            <p className="text-sm text-foreground">
              <span className="font-semibold">Note:</span> This is a simplified authentication
              system similar to JupyterLab. The server generates a single token on startup that
              grants full access. This is designed for single-tenant deployments and development
              environments.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'

export default function AgentConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold">Agent Configuration</h2>
        <p className="text-muted-foreground mt-1">
          Edit agent prompts, capabilities, and constraints
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent Configurations</CardTitle>
          <CardDescription>
            Manage agent settings, prompts, and capabilities
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Agent configuration UI implementation pending...
          </p>
          {/* TODO: Implement agent configuration editor */}
          {/* - List all agents */}
          {/* - Edit agent model and timeout */}
          {/* - Configure MCP servers */}
          {/* - Set agent capabilities */}
          {/* - Configure agent constraints */}
        </CardContent>
      </Card>
    </div>
  )
}

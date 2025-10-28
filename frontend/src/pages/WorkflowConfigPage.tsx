import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'

export default function WorkflowConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold">Workflow Configuration</h2>
        <p className="text-muted-foreground mt-1">
          Configure workflow pipelines, stages, and transitions
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Workflow Pipelines</CardTitle>
          <CardDescription>
            Add, edit, and delete workflow stages and configure stage transitions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Workflow configuration UI implementation pending...
          </p>
          {/* TODO: Implement workflow pipeline editor */}
          {/* - List existing pipelines */}
          {/* - Add/edit pipeline stages */}
          {/* - Configure stage transitions */}
          {/* - Assign agents to stages */}
          {/* - Configure entry conditions */}
        </CardContent>
      </Card>
    </div>
  )
}

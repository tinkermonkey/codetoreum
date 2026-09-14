import { KeyRound } from 'lucide-react'

export default function AuthRequiredPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-lg space-y-8">
        <div className="space-y-3 text-center sm:text-left">
          <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Codetoreum
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Sign in with your server token
          </h1>
          <p className="text-sm text-muted-foreground text-balance">
            Open the dashboard using the access URL printed when the API starts. The token is
            exchanged for a secure cookie automatically.
          </p>
        </div>

        <div className="surface-panel space-y-5 p-6 shadow-soft">
          <div className="flex gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <KeyRound className="h-4 w-4" aria-hidden />
            </div>
            <ol className="list-decimal space-y-2 pl-4 text-sm text-muted-foreground marker:text-foreground">
              <li>Start the API with <span className="font-mono text-foreground">codetoreum-server</span></li>
              <li>Copy the <span className="font-medium text-foreground">Access URL</span> from the logs</li>
              <li>Open it in this browser (port 3010 for the UI)</li>
            </ol>
          </div>

          <div className="rounded-lg bg-secondary/80 p-3">
            <p className="mb-2 text-xs font-medium text-foreground">Example</p>
            <pre className="overflow-x-auto font-mono text-[11px] leading-relaxed text-muted-foreground">
{`Authentication token: eyJhbG…
Access URL: http://127.0.0.1:3010/?token=eyJhbG…`}
            </pre>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground sm:text-left">
          Single-tenant development auth — anyone with the token has full API access.
        </p>
      </div>
    </div>
  )
}

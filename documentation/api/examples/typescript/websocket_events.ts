/**
 * Example: Real-time event streaming via WebSocket
 *
 * This example demonstrates how to connect to the WebSocket endpoint
 * and receive real-time events about workflows, executions, and work items.
 *
 * Install: npm install ws @types/ws
 */
import WebSocket from "ws";

// Configuration
const WS_URL = "ws://localhost:8000/api/v2/events/stream";
const API_TOKEN = "your_token_here"; // Get from server startup logs

// Type definitions
interface CodetoreumEvent {
  type: string;
  timestamp: string;
  data: Record<string, any>;
}

type EventHandler = (event: CodetoreumEvent) => void | Promise<void>;

/**
 * WebSocket client for Codetoreum event streaming
 */
class CodetoreumEventStream {
  private ws: WebSocket | null = null;
  private handlers: Map<string, EventHandler[]> = new Map();
  private url: string;

  constructor(token: string, baseUrl: string = WS_URL) {
    this.url = `${baseUrl}?token=${token}`;
  }

  /**
   * Connect to the WebSocket
   */
  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      console.log(`Connecting to ${this.url}...`);

      this.ws = new WebSocket(this.url);

      this.ws.on("open", () => {
        console.log("✓ Connected to event stream");
        resolve();
      });

      this.ws.on("error", (error) => {
        console.error("WebSocket error:", error);
        reject(error);
      });

      this.ws.on("close", () => {
        console.log("✓ Disconnected from event stream");
      });

      this.ws.on("message", (data: WebSocket.Data) => {
        this.handleMessage(data.toString());
      });
    });
  }

  /**
   * Disconnect from the WebSocket
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * Register event handler for specific event type
   */
  on(eventType: string, handler: EventHandler): void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, []);
    }
    this.handlers.get(eventType)!.push(handler);
  }

  /**
   * Register handler for all events
   */
  onAll(handler: EventHandler): void {
    this.on("*", handler);
  }

  /**
   * Handle incoming message
   */
  private async handleMessage(message: string): Promise<void> {
    try {
      const event: CodetoreumEvent = JSON.parse(message);
      const eventType = event.type || "unknown";

      const timestamp = new Date().toLocaleTimeString();
      console.log(`[${timestamp}] Received: ${eventType}`);

      // Call specific handlers
      const specificHandlers = this.handlers.get(eventType) || [];
      for (const handler of specificHandlers) {
        await handler(event);
      }

      // Call wildcard handlers
      const wildcardHandlers = this.handlers.get("*") || [];
      for (const handler of wildcardHandlers) {
        await handler(event);
      }
    } catch (error) {
      console.error("Error handling message:", error);
    }
  }

  /**
   * Listen for events (keeps connection open)
   */
  async listen(): Promise<void> {
    if (!this.ws) {
      throw new Error("Not connected. Call connect() first.");
    }

    return new Promise((resolve, reject) => {
      if (!this.ws) {
        reject(new Error("WebSocket not connected"));
        return;
      }

      this.ws.on("close", () => resolve());
      this.ws.on("error", reject);
    });
  }
}

// Example event handlers

async function handleWorkflowStarted(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  🚀 Workflow started:`);
  console.log(`     Run ID: ${data.workflow_run_id}`);
  console.log(`     Work Item: ${data.work_item_id}`);
  console.log(`     Workflow: ${data.workflow_name}`);
}

async function handleWorkflowCompleted(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  ✓ Workflow completed:`);
  console.log(`     Run ID: ${data.workflow_run_id}`);
  console.log(`     Status: ${data.status}`);
  console.log(`     Duration: ${data.duration_seconds}s`);
}

async function handleExecutionStarted(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  ▶ Execution started:`);
  console.log(`     Execution ID: ${data.execution_id}`);
  console.log(`     Agent: ${data.agent_id}`);
  console.log(`     Stage: ${data.stage_name}`);
}

async function handleExecutionProgress(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  const progress = data.progress || {};
  const pct = progress.percentage || 0;
  const step = progress.current_step || "";
  console.log(`  ⏳ Execution progress: ${pct}% - ${step}`);
}

async function handleExecutionCompleted(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  ✓ Execution completed:`);
  console.log(`     Execution ID: ${data.execution_id}`);
  console.log(`     Status: ${data.status}`);
}

async function handleExecutionFailed(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  ✗ Execution failed:`);
  console.log(`     Execution ID: ${data.execution_id}`);
  console.log(`     Error: ${data.error_message}`);
}

async function handleWorkItemUpdated(event: CodetoreumEvent): Promise<void> {
  const data = event.data;
  console.log(`  📝 Work item updated:`);
  console.log(`     Work Item ID: ${data.work_item_id}`);
  console.log(`     Status: ${data.status}`);
  console.log(`     Stage: ${data.workflow_stage}`);
}

async function logAllEvents(event: CodetoreumEvent): Promise<void> {
  // Pretty print the entire event (for debugging)
  console.log(`  Raw event:`, JSON.stringify(event, null, 2));
}

/**
 * Main example: Monitor all workflow and execution events
 */
async function main() {
  const client = new CodetoreumEventStream(API_TOKEN);

  // Register event handlers
  client.on("workflow.started", handleWorkflowStarted);
  client.on("workflow.completed", handleWorkflowCompleted);
  client.on("execution.started", handleExecutionStarted);
  client.on("execution.progress", handleExecutionProgress);
  client.on("execution.completed", handleExecutionCompleted);
  client.on("execution.failed", handleExecutionFailed);
  client.on("work_item.updated", handleWorkItemUpdated);

  // Optionally log all events for debugging
  // client.onAll(logAllEvents);

  // Connect and listen
  await client.connect();

  console.log("\n📡 Listening for events... (Press Ctrl+C to stop)\n");

  // Handle graceful shutdown
  process.on("SIGINT", () => {
    console.log("\n\nStopping...");
    client.disconnect();
    process.exit(0);
  });

  // Listen for events (this keeps the process running)
  try {
    await client.listen();
  } catch (error) {
    console.error("Error:", error);
    client.disconnect();
    process.exit(1);
  }
}

/**
 * Example: Monitor only specific execution
 */
async function exampleFilteredMonitoring() {
  const client = new CodetoreumEventStream(API_TOKEN);

  // Track specific execution
  const targetExecutionId = "exec_abc123";

  const handleTargetExecution = async (event: CodetoreumEvent) => {
    const data = event.data;
    if (data.execution_id === targetExecutionId) {
      console.log(`Target execution event: ${event.type}`);
      console.log(`  Data:`, JSON.stringify(data, null, 2));
    }
  };

  // Register handler for all execution events
  client.on("execution.started", handleTargetExecution);
  client.on("execution.progress", handleTargetExecution);
  client.on("execution.completed", handleTargetExecution);
  client.on("execution.failed", handleTargetExecution);

  await client.connect();

  try {
    await client.listen();
  } finally {
    client.disconnect();
  }
}

// Run if executed directly
if (require.main === module) {
  // Run main example
  main();

  // Or run filtered monitoring example
  // exampleFilteredMonitoring();
}

export { CodetoreumEventStream };
export type { CodetoreumEvent, EventHandler };

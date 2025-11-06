/**
 * Example: List and monitor agent executions
 *
 * This example demonstrates how to list executions, filter by status,
 * and retrieve execution logs using TypeScript.
 */

// Configuration
const BASE_URL = "http://localhost:8000";
const API_TOKEN = "your_token_here"; // Get from server startup logs

// Type definitions
interface Execution {
  id: string;
  agent_id: string;
  work_item_id: string;
  workflow_run_id: string;
  stage_name: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  container_id?: string;
  progress?: {
    current_step: string;
    total_steps: number;
    percentage: number;
  };
  error_message?: string;
}

interface ExecutionListResponse {
  items: Execution[];
  total: number;
  offset: number;
  limit: number;
}

interface ExecutionFilters {
  status?: string;
  work_item_id?: string;
  agent_id?: string;
  workflow_run_id?: string;
  offset?: number;
  limit?: number;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}

interface ExecutionLogs {
  execution_id: string;
  logs: string[];
  total_lines: number;
}

/**
 * List agent executions with filtering and pagination
 */
async function listExecutions(
  filters?: ExecutionFilters
): Promise<ExecutionListResponse> {
  const params = new URLSearchParams();

  // Add filters
  if (filters) {
    if (filters.status) params.append("status", filters.status);
    if (filters.work_item_id)
      params.append("work_item_id", filters.work_item_id);
    if (filters.agent_id) params.append("agent_id", filters.agent_id);
    if (filters.workflow_run_id)
      params.append("workflow_run_id", filters.workflow_run_id);
    if (filters.offset !== undefined)
      params.append("offset", filters.offset.toString());
    if (filters.limit !== undefined)
      params.append("limit", filters.limit.toString());
    if (filters.sort_by) params.append("sort_by", filters.sort_by);
    if (filters.sort_order) params.append("sort_order", filters.sort_order);
  }

  const url = `${BASE_URL}/api/v2/executions/?${params.toString()}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to list executions: ${error.detail}`);
  }

  return await response.json();
}

/**
 * Get detailed information about a specific execution
 */
async function getExecutionDetails(executionId: string): Promise<Execution> {
  const url = `${BASE_URL}/api/v2/executions/${executionId}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to get execution details: ${error.detail}`);
  }

  return await response.json();
}

/**
 * Get execution logs
 */
async function getExecutionLogs(
  executionId: string,
  tail?: number
): Promise<ExecutionLogs> {
  const params = new URLSearchParams();
  if (tail !== undefined) {
    params.append("tail", tail.toString());
  }

  const url = `${BASE_URL}/api/v2/executions/${executionId}/logs?${params.toString()}`;

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to get execution logs: ${error.detail}`);
  }

  return await response.json();
}

/**
 * Wait for an execution to complete
 */
async function waitForExecution(
  executionId: string,
  options: {
    checkInterval?: number; // seconds
    timeout?: number; // seconds
    printLogs?: boolean;
    onProgress?: (execution: Execution) => void;
  } = {}
): Promise<Execution> {
  const {
    checkInterval = 5,
    timeout = 3600,
    printLogs = true,
    onProgress,
  } = options;

  const startTime = Date.now();
  let lastLogCount = 0;

  while (true) {
    // Check timeout
    if (Date.now() - startTime > timeout * 1000) {
      throw new Error(
        `Execution ${executionId} did not complete within ${timeout}s`
      );
    }

    // Get execution status
    const execution = await getExecutionDetails(executionId);
    const status = execution.status;

    const timestamp = new Date().toLocaleTimeString();
    console.log(`[${timestamp}] Status: ${status}`, end="");

    if (execution.progress) {
      const pct = execution.progress.percentage;
      console.log(` - ${pct}%`);
    } else {
      console.log();
    }

    // Call progress callback
    if (onProgress) {
      onProgress(execution);
    }

    // Print new logs if requested
    if (printLogs) {
      const logsData = await getExecutionLogs(executionId);
      const logs = logsData.logs;
      const newLogs = logs.slice(lastLogCount);

      for (const log of newLogs) {
        console.log(`  ${log}`);
      }

      lastLogCount = logs.length;
    }

    // Check if completed
    if (["completed", "failed", "cancelled"].includes(status)) {
      return execution;
    }

    // Wait before next check
    await new Promise((resolve) => setTimeout(resolve, checkInterval * 1000));
  }
}

/**
 * Terminate a running execution
 */
async function terminateExecution(executionId: string): Promise<Execution> {
  const url = `${BASE_URL}/api/v2/executions/${executionId}/terminate`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Failed to terminate execution: ${error.detail}`);
  }

  console.log(`✓ Terminated execution: ${executionId}`);
  return await response.json();
}

// Example usage
async function main() {
  try {
    console.log("=== Listing Running Executions ===\n");

    // List all running executions
    const running = await listExecutions({ status: "running" });
    console.log(`Found ${running.total} running execution(s)`);

    for (const execution of running.items) {
      console.log(`\n  ID: ${execution.id}`);
      console.log(`  Agent: ${execution.agent_id}`);
      console.log(`  Work Item: ${execution.work_item_id}`);
      console.log(`  Status: ${execution.status}`);
      console.log(`  Started: ${execution.started_at}`);
    }

    // List recent completed executions
    console.log("\n\n=== Recent Completed Executions ===\n");
    const completed = await listExecutions({
      status: "completed",
      limit: 5,
      sort_by: "completed_at",
      sort_order: "desc",
    });
    console.log(`Found ${completed.total} completed execution(s)`);

    for (const execution of completed.items) {
      console.log(`\n  ID: ${execution.id}`);
      console.log(`  Status: ${execution.status}`);
      console.log(`  Duration: ${execution.duration_seconds || "N/A"}s`);
    }

    // Monitor a specific execution (if any running)
    if (running.items.length > 0) {
      const executionId = running.items[0].id;
      console.log(`\n\n=== Monitoring Execution ${executionId} ===\n`);

      try {
        const finalStatus = await waitForExecution(executionId, {
          checkInterval: 5,
          timeout: 300, // 5 minutes
          printLogs: true,
          onProgress: (execution) => {
            // Custom progress handler
            if (execution.progress) {
              console.log(
                `Progress: ${execution.progress.current_step} (${execution.progress.percentage}%)`
              );
            }
          },
        });

        console.log(
          `\n✓ Execution completed with status: ${finalStatus.status}`
        );
      } catch (error) {
        console.log(`\n⚠ ${error}`);
      }
    }

    // List failed executions for debugging
    console.log("\n\n=== Recent Failed Executions ===\n");
    const failed = await listExecutions({
      status: "failed",
      limit: 5,
      sort_by: "completed_at",
      sort_order: "desc",
    });
    console.log(`Found ${failed.total} failed execution(s)`);

    for (const execution of failed.items) {
      console.log(`\n  ID: ${execution.id}`);
      console.log(`  Agent: ${execution.agent_id}`);
      console.log(`  Failed at: ${execution.completed_at || "N/A"}`);

      if (execution.error_message) {
        console.log(`  Error: ${execution.error_message}`);
      }

      // Get last 5 lines of logs
      const logsData = await getExecutionLogs(execution.id, 10);
      if (logsData.logs.length > 0) {
        console.log("  Last logs:");
        const lastLogs = logsData.logs.slice(-5);
        for (const log of lastLogs) {
          console.log(`    ${log}`);
        }
      }
    }
  } catch (error) {
    console.error("Error:", error);
    process.exit(1);
  }
}

// Run if executed directly
if (require.main === module) {
  main();
}

export {
  listExecutions,
  getExecutionDetails,
  getExecutionLogs,
  waitForExecution,
  terminateExecution,
};
export type { Execution, ExecutionListResponse, ExecutionFilters };

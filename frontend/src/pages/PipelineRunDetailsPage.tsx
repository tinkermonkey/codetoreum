/**
 * PipelineRunDetailsPage
 *
 * Main page for viewing workflow run details with sidebar and event timeline.
 * Route: /workflows/runs/:id?
 */

import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

import { WorkflowRunSidebar } from '../components/workflow-runs/WorkflowRunSidebar';
import { WorkflowRunDetails } from '../components/workflow-runs/WorkflowRunDetails';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { useWorkflowRunsUIStore } from '../store/workflowRunsUIStore';
import { useWorkflowWebSocket } from '../hooks/useWorkflowWebSocket';
import { useAuthStore } from '../store/authStore';

export function PipelineRunDetailsPage(): React.ReactElement {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { selectedWorkflowId, setSelectedWorkflow } = useWorkflowRunsUIStore();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuthStore();

  // Enable real-time updates via WebSocket
  useWorkflowWebSocket(isAuthenticated, isAuthLoading);

  // Sync URL param with store on mount and when URL changes
  useEffect(() => {
    // Direct navigation to /workflows/runs/123 should update store
    if (id) {
      setSelectedWorkflow(id);
    }
  }, [id, setSelectedWorkflow]);

  // Update URL when selection changes from UI interaction
  useEffect(() => {
    // Only navigate if there's a mismatch between store and URL
    if (selectedWorkflowId !== id) {
      if (selectedWorkflowId) {
        navigate(`/workflows/runs/${selectedWorkflowId}`, { replace: true });
      } else if (id) {
        // User deselected, go back to list view
        navigate('/workflows/runs', { replace: true });
      }
    }
  }, [selectedWorkflowId, id, navigate]);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <ErrorBoundary>
        <div className="w-96 flex-shrink-0">
          <WorkflowRunSidebar />
        </div>
      </ErrorBoundary>

      {/* Main content */}
      <ErrorBoundary>
        <div className="flex-1 overflow-hidden">
          <WorkflowRunDetails workflowRunId={selectedWorkflowId} />
        </div>
      </ErrorBoundary>
    </div>
  );
}

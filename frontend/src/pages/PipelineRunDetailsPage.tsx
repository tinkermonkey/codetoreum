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
import { useWorkflowRunsUIStore } from '../store/workflowRunsUIStore';
import { useWorkflowWebSocket } from '../hooks/useWorkflowWebSocket';
import { useAuthStore } from '../store/authStore';

export function PipelineRunDetailsPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { selectedWorkflowId, setSelectedWorkflow } = useWorkflowRunsUIStore();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuthStore();

  // Enable real-time updates via WebSocket
  useWorkflowWebSocket(isAuthenticated, isAuthLoading);

  // Sync URL param with store
  useEffect(() => {
    if (id && id !== selectedWorkflowId) {
      setSelectedWorkflow(id);
    } else if (!id && selectedWorkflowId) {
      setSelectedWorkflow(null);
    }
  }, [id, selectedWorkflowId, setSelectedWorkflow]);

  // Update URL when selection changes
  useEffect(() => {
    if (selectedWorkflowId && selectedWorkflowId !== id) {
      navigate(`/workflows/runs/${selectedWorkflowId}`, { replace: true });
    } else if (!selectedWorkflowId && id) {
      navigate('/workflows/runs', { replace: true });
    }
  }, [selectedWorkflowId, id, navigate]);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900">
      {/* Sidebar */}
      <div className="w-96 flex-shrink-0">
        <WorkflowRunSidebar />
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        <WorkflowRunDetails workflowRunId={selectedWorkflowId} />
      </div>
    </div>
  );
}

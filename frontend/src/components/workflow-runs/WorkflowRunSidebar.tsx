/**
 * WorkflowRunSidebar Component
 *
 * Left sidebar with tabs, search, and workflow run list.
 */

import React from 'react';
import { Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { useWorkflowRunsUIStore, WorkflowRunTab } from '../../store/workflowRunsUIStore';
import { useActiveWorkflowRuns, useCompletedWorkflowRuns } from '../../hooks/useWorkflowRuns';
import { WorkflowRunList } from './WorkflowRunList';
import { cn } from '../../lib/utils';

export function WorkflowRunSidebar() {
  const {
    selectedTab,
    selectedWorkflowId,
    searchQuery,
    completedOffset,
    setSelectedTab,
    setSelectedWorkflow,
    setSearchQuery,
    setCompletedOffset,
  } = useWorkflowRunsUIStore();

  const { data: activeRuns, isLoading: isLoadingActive } = useActiveWorkflowRuns(
    { search: searchQuery }
  );

  const {
    data: completedResponse,
    isLoading: isLoadingCompleted,
  } = useCompletedWorkflowRuns({
    search: searchQuery,
    offset: completedOffset,
    limit: 10,
  });

  const completedRuns = completedResponse?.runs ?? [];
  const total = completedResponse?.total ?? 0;
  const hasNextPage = completedOffset + 10 < total;
  const hasPreviousPage = completedOffset > 0;

  const tabs: { id: WorkflowRunTab; label: string }[] = [
    { id: 'active', label: 'Active' },
    { id: 'completed', label: 'Completed' },
  ];

  const currentRuns = selectedTab === 'active' ? activeRuns ?? [] : completedRuns;
  const isLoading = selectedTab === 'active' ? isLoadingActive : isLoadingCompleted;

  return (
    <div className="flex flex-col h-full border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold mb-3">Workflow Runs</h2>

        {/* Tabs */}
        <div className="flex gap-2 mb-3">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedTab(tab.id)}
              className={cn(
                'flex-1 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                selectedTab === tab.id
                  ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search runs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-600 dark:text-white"
          />
        </div>
      </div>

      {/* Run List */}
      <div className="flex-1 overflow-y-auto p-4">
        <WorkflowRunList
          runs={currentRuns}
          selectedRunId={selectedWorkflowId}
          onSelectRun={setSelectedWorkflow}
          isLoading={isLoading}
          emptyMessage={
            searchQuery
              ? 'No matching workflow runs'
              : selectedTab === 'active'
              ? 'No active workflow runs'
              : 'No completed workflow runs'
          }
        />
      </div>

      {/* Pagination (Completed only) */}
      {selectedTab === 'completed' && total > 0 && (
        <div className="p-4 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">
              {completedOffset + 1}-{Math.min(completedOffset + 10, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setCompletedOffset(Math.max(0, completedOffset - 10))}
                disabled={!hasPreviousPage}
                className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => setCompletedOffset(completedOffset + 10)}
                disabled={!hasNextPage}
                className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Zustand store for Workflow Runs UI state
 *
 * Manages UI state for the Pipeline Run Details page:
 * - Selected tab (active/completed)
 * - Selected workflow run
 * - Search query
 * - Pagination offset
 */

import { create } from 'zustand';

export type WorkflowRunTab = 'active' | 'completed';

interface WorkflowRunsUIState {
  // UI State
  selectedTab: WorkflowRunTab;
  selectedWorkflowId: string | null;
  searchQuery: string;
  completedOffset: number;

  // Actions
  setSelectedTab: (tab: WorkflowRunTab) => void;
  setSelectedWorkflow: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setCompletedOffset: (offset: number) => void;
  resetSearch: () => void;
  reset: () => void;
}

const INITIAL_STATE = {
  selectedTab: 'active' as WorkflowRunTab,
  selectedWorkflowId: null,
  searchQuery: '',
  completedOffset: 0,
};

export const useWorkflowRunsUIStore = create<WorkflowRunsUIState>((set) => ({
  ...INITIAL_STATE,

  setSelectedTab: (tab) => set({ selectedTab: tab }),

  setSelectedWorkflow: (id) => set({ selectedWorkflowId: id }),

  setSearchQuery: (query) =>
    set({ searchQuery: query, completedOffset: 0 }), // Reset pagination on search

  setCompletedOffset: (offset) => set({ completedOffset: offset }),

  resetSearch: () => set({ searchQuery: '', completedOffset: 0 }),

  reset: () => set(INITIAL_STATE),
}));

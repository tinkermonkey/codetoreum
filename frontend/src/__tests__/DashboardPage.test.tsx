/**
 * Integration tests for DashboardPage component.
 *
 * Tests dashboard rendering, work item display, filtering, WebSocket updates,
 * execution progress, error handling, and loading states.
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { act } from 'react-dom/test-utils';
import '@testing-library/jest-dom';
import DashboardPage from '../pages/DashboardPage';
import { useWebSocket } from '../hooks/useWebSocket';
import { useAuth } from '../hooks/useAuth';

// Mock hooks
jest.mock('../hooks/useWebSocket');
jest.mock('../hooks/useAuth');

const mockUseWebSocket = useWebSocket as jest.MockedFunction<typeof useWebSocket>;
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe('DashboardPage', () => {
  const mockWorkItems = [
    {
      id: 'work-item-1',
      title: 'Fix authentication bug',
      status: 'in_progress',
      assignedAgent: 'agent-coder',
      progress: 0.45,
      stage: 'implementation',
    },
    {
      id: 'work-item-2',
      title: 'Add user profile feature',
      status: 'pending',
      assignedAgent: null,
      progress: 0,
      stage: null,
    },
    {
      id: 'work-item-3',
      title: 'Update documentation',
      status: 'completed',
      assignedAgent: 'agent-writer',
      progress: 1.0,
      stage: 'completed',
    },
  ];

  beforeEach(() => {
    // Reset mocks before each test
    jest.clearAllMocks();

    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: 'user-123', username: 'testuser' },
      loading: false,
      login: jest.fn(),
      logout: jest.fn(),
    });

    mockUseWebSocket.mockReturnValue({
      connected: true,
      messages: [],
      sendMessage: jest.fn(),
      error: null,
    });
  });

  describe('Rendering', () => {
    it('should render dashboard layout correctly', () => {
      render(<DashboardPage />);

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Work Items')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Filter work items...')).toBeInTheDocument();
    });

    it('should display loading state initially', () => {
      render(<DashboardPage />);

      expect(screen.getByText('Loading work items...')).toBeInTheDocument();
    });

    it('should display work items from WebSocket', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('Fix authentication bug')).toBeInTheDocument();
        expect(screen.getByText('Add user profile feature')).toBeInTheDocument();
        expect(screen.getByText('Update documentation')).toBeInTheDocument();
      });
    });

    it('should display empty state when no work items', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: [] },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('No work items found')).toBeInTheDocument();
      });
    });
  });

  describe('Filtering', () => {
    it('should filter work items by status', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      // Select "in_progress" filter
      const statusFilter = screen.getByLabelText('Status filter');
      fireEvent.change(statusFilter, { target: { value: 'in_progress' } });

      await waitFor(() => {
        expect(screen.getByText('Fix authentication bug')).toBeInTheDocument();
        expect(screen.queryByText('Add user profile feature')).not.toBeInTheDocument();
        expect(screen.queryByText('Update documentation')).not.toBeInTheDocument();
      });
    });

    it('should filter work items by search term', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      const searchInput = screen.getByPlaceholderText('Filter work items...');
      fireEvent.change(searchInput, { target: { value: 'authentication' } });

      await waitFor(() => {
        expect(screen.getByText('Fix authentication bug')).toBeInTheDocument();
        expect(screen.queryByText('Add user profile feature')).not.toBeInTheDocument();
        expect(screen.queryByText('Update documentation')).not.toBeInTheDocument();
      });
    });
  });

  describe('Work Item Selection', () => {
    it('should handle work item selection', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('Fix authentication bug')).toBeInTheDocument();
      });

      // Click on work item
      fireEvent.click(screen.getByText('Fix authentication bug'));

      await waitFor(() => {
        expect(screen.getByText('Work Item Details')).toBeInTheDocument();
        expect(screen.getByText('Status: in_progress')).toBeInTheDocument();
      });
    });

    it('should close work item details on cancel', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('Fix authentication bug')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Fix authentication bug'));

      await waitFor(() => {
        expect(screen.getByText('Work Item Details')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Close'));

      await waitFor(() => {
        expect(screen.queryByText('Work Item Details')).not.toBeInTheDocument();
      });
    });
  });

  describe('Execution Progress', () => {
    it('should display execution progress for in-progress work items', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('45%')).toBeInTheDocument();
      });
    });

    it('should update progress on WebSocket events', async () => {
      const mockSendMessage = jest.fn();

      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
          {
            type: 'execution_progress',
            data: {
              workItemId: 'work-item-1',
              progress: 0.75,
            },
          },
        ],
        sendMessage: mockSendMessage,
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('75%')).toBeInTheDocument();
      });
    });
  });

  describe('WebSocket Updates', () => {
    it('should handle new work item from WebSocket', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
          {
            type: 'work_item_created',
            data: {
              workItem: {
                id: 'work-item-4',
                title: 'New work item',
                status: 'pending',
              },
            },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.getByText('New work item')).toBeInTheDocument();
      });
    });

    it('should handle work item status change from WebSocket', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
          {
            type: 'work_item_status_changed',
            data: {
              workItemId: 'work-item-2',
              oldStatus: 'pending',
              newStatus: 'in_progress',
            },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        const workItem = screen.getByText('Add user profile feature').closest('div');
        expect(workItem).toHaveTextContent('in_progress');
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message when WebSocket connection fails', () => {
      mockUseWebSocket.mockReturnValue({
        connected: false,
        messages: [],
        sendMessage: jest.fn(),
        error: 'Connection failed',
      });

      render(<DashboardPage />);

      expect(screen.getByText('Connection error: Connection failed')).toBeInTheDocument();
    });

    it('should show retry button on connection error', () => {
      mockUseWebSocket.mockReturnValue({
        connected: false,
        messages: [],
        sendMessage: jest.fn(),
        error: 'Connection failed',
      });

      render(<DashboardPage />);

      expect(screen.getByText('Retry Connection')).toBeInTheDocument();
    });

    it('should retry connection on button click', async () => {
      const mockRetry = jest.fn();

      mockUseWebSocket.mockReturnValue({
        connected: false,
        messages: [],
        sendMessage: jest.fn(),
        error: 'Connection failed',
        retry: mockRetry,
      });

      render(<DashboardPage />);

      fireEvent.click(screen.getByText('Retry Connection'));

      await waitFor(() => {
        expect(mockRetry).toHaveBeenCalled();
      });
    });
  });

  describe('Loading States', () => {
    it('should show loading spinner while fetching data', () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      expect(screen.getByText('Loading work items...')).toBeInTheDocument();
    });

    it('should hide loading spinner after data loads', async () => {
      mockUseWebSocket.mockReturnValue({
        connected: true,
        messages: [
          {
            type: 'work_items_update',
            data: { workItems: mockWorkItems },
          },
        ],
        sendMessage: jest.fn(),
        error: null,
      });

      render(<DashboardPage />);

      await waitFor(() => {
        expect(screen.queryByText('Loading work items...')).not.toBeInTheDocument();
      });
    });
  });
});

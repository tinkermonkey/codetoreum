/**
 * EventTimeline Component
 *
 * Displays a chronological timeline of workflow events.
 */

import React from 'react';
import { WorkflowEvent } from '../../types/workflow-event';
import { EventCard } from './EventCard';
import { Loader2, Activity } from 'lucide-react';

interface EventTimelineProps {
  events: WorkflowEvent[];
  isLoading?: boolean;
}

export function EventTimeline({ events, isLoading = false }: EventTimelineProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <Activity className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-3" />
        <p className="text-sm text-gray-500 dark:text-gray-400">No events yet</p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          Events will appear here as the workflow executes
        </p>
      </div>
    );
  }

  // Sort events by timestamp (newest first)
  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return (
    <div className="py-4">
      {sortedEvents.map((event, index) => (
        <EventCard
          key={event.id}
          event={event}
          isLast={index === sortedEvents.length - 1}
        />
      ))}
    </div>
  );
}

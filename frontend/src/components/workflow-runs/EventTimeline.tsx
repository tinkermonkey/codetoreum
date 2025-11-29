/**
 * EventTimeline Component
 *
 * Displays a chronological timeline of workflow events with pagination.
 */

import React, { useState, useMemo } from 'react';
import { Loader2, Activity, ChevronDown } from 'lucide-react';

import { WorkflowEvent } from '../../types/workflow-event';
import { EventCard } from './EventCard';
import { Button } from '../ui/button';

interface EventTimelineProps {
  events: WorkflowEvent[];
  isLoading?: boolean;
  initialPageSize?: number;
}

export function EventTimeline({
  events,
  isLoading = false,
  initialPageSize = 20
}: EventTimelineProps): React.ReactElement {
  const [displayCount, setDisplayCount] = useState(initialPageSize);

  // Sort events by timestamp (newest first) - memoized to avoid re-sorting
  const sortedEvents = useMemo(() =>
    [...events].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    ),
    [events]
  );

  const visibleEvents = useMemo(() =>
    sortedEvents.slice(0, displayCount),
    [sortedEvents, displayCount]
  );

  const hasMore = sortedEvents.length > displayCount;

  const handleLoadMore = (): void => {
    setDisplayCount(prev => Math.min(prev + initialPageSize, sortedEvents.length));
  };

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

  return (
    <div className="py-4">
      <div className="transition-all duration-300">
        {visibleEvents.map((event, index) => (
          <EventCard
            key={event.id}
            event={event}
            isLast={index === visibleEvents.length - 1 && !hasMore}
          />
        ))}
      </div>

      {hasMore && (
        <div className="flex justify-center pt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadMore}
            className="gap-2"
          >
            <ChevronDown className="w-4 h-4" />
            Load More ({sortedEvents.length - displayCount} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}

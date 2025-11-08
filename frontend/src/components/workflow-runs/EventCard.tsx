/**
 * EventCard Component
 *
 * Displays a single workflow event in the timeline.
 */

import React from 'react';
import { format } from 'date-fns';
import { Terminal } from 'lucide-react';

import { WorkflowEvent } from '../../types/workflow-event';
import { EventIcon, getEventLabel } from './EventIcon';

interface EventCardProps {
  event: WorkflowEvent;
  isLast?: boolean;
}

export const EventCard = React.memo<EventCardProps>(({ event, isLast = false }) => {
  const timestamp = format(new Date(event.timestamp), 'HH:mm:ss');

  return (
    <div className="relative flex gap-4 pb-6">
      {/* Timeline connector */}
      {!isLast && (
        <div className="absolute left-5 top-12 bottom-0 w-px bg-gray-200 dark:bg-gray-700" />
      )}

      {/* Icon */}
      <div className="flex-shrink-0 z-10">
        <EventIcon eventType={event.eventType} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-1">
        <div className="flex items-start justify-between gap-4 mb-2">
          <div>
            <h4 className="text-sm font-semibold">{getEventLabel(event.eventType)}</h4>
            {(event.agentName || event.stageName) && (
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                {event.agentName && <span className="font-medium">{event.agentName}</span>}
                {event.agentName && event.stageName && <span> • </span>}
                {event.stageName && <span>{event.stageName}</span>}
              </p>
            )}
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-500 flex-shrink-0">
            {timestamp}
          </span>
        </div>

        {/* Event data */}
        {event.data && Object.keys(event.data).length > 0 && (
          <div className="mt-2 space-y-2">
            {event.data.message && (
              <p className="text-sm text-gray-700 dark:text-gray-300">{event.data.message}</p>
            )}

            {event.data.errorMessage && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <div className="flex items-start gap-2">
                  <Terminal className="w-4 h-4 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-800 dark:text-red-200 font-mono break-all">
                    {event.data.errorMessage}
                  </p>
                </div>
                {event.data.exitCode !== undefined && (
                  <p className="text-xs text-red-600 dark:text-red-400 mt-2">
                    Exit code: {event.data.exitCode}
                  </p>
                )}
              </div>
            )}

            {event.data.decision && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
                <p className="text-xs font-medium text-blue-700 dark:text-blue-300 mb-1">
                  Decision
                </p>
                <p className="text-sm text-blue-900 dark:text-blue-100">{event.data.decision}</p>
              </div>
            )}

            {event.data.metadata && Object.keys(event.data.metadata).length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100">
                  View metadata
                </summary>
                <pre className="mt-2 p-2 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto">
                  {JSON.stringify(event.data.metadata, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

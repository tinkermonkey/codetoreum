import { useEffect, useState, useCallback, useRef } from 'react'
import { io } from 'socket.io-client'
import { SocketContext } from './SocketContextValue'

export function SocketProvider({ children }) {
  const [socket, setSocket] = useState(null)
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [logs, setLogs] = useState([])
  const [stats, setStats] = useState({
    totalEvents: 0,
    activeTasks: 0,
    totalTokens: 0,
    avgLatency: 0,
  })

  // Use refs to persist data across renders
  const activeTasksRef = useRef(new Set())
  const apiLatenciesRef = useRef([])

  // Load history and calculate initial stats
  const loadHistoryAndStats = useCallback(() => {
    // Helper function to calculate stats from historical events
    const calculateStatsFromHistory = (historicalEvents) => {
      let totalEvents = 0
      let totalTokens = 0
      const latencies = []

      historicalEvents.forEach(event => {
        totalEvents++

        if (event.event_type === 'task_received') {
          activeTasksRef.current.add(event.task_id)
        } else if (event.event_type === 'agent_completed' || event.event_type === 'agent_failed') {
          activeTasksRef.current.delete(event.task_id)
        }

        if (event.event_type === 'claude_api_call_completed') {
          totalTokens += event.data?.total_tokens || 0
          const latency = event.data?.duration_ms || 0
          if (latency > 0) {
            latencies.push(latency)
          }
        }
      })

      // Keep only last 10 latencies for average
      const recentLatencies = latencies.slice(-10)
      apiLatenciesRef.current.length = 0
      apiLatenciesRef.current.push(...recentLatencies)

      const avgLatency = recentLatencies.length > 0
        ? Math.round(recentLatencies.reduce((a, b) => a + b, 0) / recentLatencies.length)
        : 0

      setStats({
        totalEvents,
        activeTasks: activeTasksRef.current.size,
        totalTokens,
        avgLatency,
      })
    }

    // Load event history
    fetch('/history?count=50')
      .then(res => res.json())
      .then(data => {
        if (data.success && data.events) {
          setEvents(data.events.reverse())
          // Calculate stats from historical events
          calculateStatsFromHistory(data.events)
        }
      })
      .catch(err => console.error('Failed to load history:', err))

    // Load Claude logs history
    fetch('/claude-logs-history?count=100')
      .then(res => res.json())
      .then(data => {
        if (data.success && data.logs) {
          setLogs(data.logs)
        }
      })
      .catch(err => console.error('Failed to load log history:', err))
  }, [])

  const updateStatsFromEvent = useCallback((event) => {
    setStats(prev => {
      const newStats = { ...prev }
      newStats.totalEvents = prev.totalEvents + 1

      if (event.event_type === 'task_received') {
        activeTasksRef.current.add(event.task_id)
        newStats.activeTasks = activeTasksRef.current.size
      } else if (event.event_type === 'agent_completed' || event.event_type === 'agent_failed') {
        activeTasksRef.current.delete(event.task_id)
        newStats.activeTasks = activeTasksRef.current.size
      }

      if (event.event_type === 'claude_api_call_completed') {
        const tokens = event.data?.total_tokens || 0
        newStats.totalTokens = prev.totalTokens + tokens

        apiLatenciesRef.current.push(event.data?.duration_ms || 0)
        if (apiLatenciesRef.current.length > 10) apiLatenciesRef.current.shift()
        const avgLatency = apiLatenciesRef.current.reduce((a, b) => a + b, 0) / apiLatenciesRef.current.length
        newStats.avgLatency = Math.round(avgLatency)
      }

      return newStats
    })
  }, [])

  useEffect(() => {
    // In development, Vite proxies /socket.io to the observability server
    // In production, nginx handles the proxy
    const socketInstance = io({
      path: '/socket.io',
      transports: ['websocket', 'polling']
    })

    socketInstance.on('connect', () => {
      console.log('Socket connected')
      setConnected(true)
      loadHistoryAndStats()
    })

    socketInstance.on('disconnect', () => {
      console.log('Socket disconnected')
      setConnected(false)
    })

    socketInstance.on('agent_event', (event) => {
      setEvents(prev => [event, ...prev].slice(0, 50))
      updateStatsFromEvent(event)
    })

    socketInstance.on('claude_stream_event', (data) => {
      /*
      console.log('[SocketContext] Received claude_stream_event:', {
        agent: data.agent,
        timestamp: data.timestamp,
        hasEvent: !!data.event
      })
      */
      setLogs(prev => [...prev, data].slice(-200))
    })

    setSocket(socketInstance)

    return () => {
      socketInstance.close()
    }
  }, [loadHistoryAndStats, updateStatsFromEvent])

  const clearEvents = () => setEvents([])
  const clearLogs = () => setLogs([])

  return (
    <SocketContext.Provider value={{
      socket,
      connected,
      events,
      logs,
      stats,
      clearEvents,
      clearLogs
    }}>
      {children}
    </SocketContext.Provider>
  )
}

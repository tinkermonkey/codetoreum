/**
 * Formats metadata object for display in node components
 * Handles circular references and provides readable output
 */
export function formatMetadata(metadata: Record<string, any> | string | undefined): string | null {
  if (!metadata) return null

  if (typeof metadata === 'string') {
    return metadata
  }

  if (Object.keys(metadata).length === 0) {
    return null
  }

  try {
    // Handle common single-value metadata
    if (Object.keys(metadata).length === 1) {
      const key = Object.keys(metadata)[0]
      const value = metadata[key]

      if (typeof value === 'string') {
        return value
      }
      if (typeof value === 'number' || typeof value === 'boolean') {
        return String(value)
      }
    }

    // For multiple values, create a readable list
    const entries = Object.entries(metadata)
      .filter(([_, value]) => value !== null && value !== undefined)
      .slice(0, 3) // Limit to first 3 entries

    if (entries.length === 0) return null

    return entries
      .map(([key, value]) => {
        const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
        const formattedValue = typeof value === 'object'
          ? JSON.stringify(value).slice(0, 50)
          : String(value).slice(0, 50)
        return `${formattedKey}: ${formattedValue}`
      })
      .join(' • ')
  } catch (error) {
    // Handle circular references or other errors
    console.warn('Error formatting metadata:', error)
    return '[Complex metadata]'
  }
}

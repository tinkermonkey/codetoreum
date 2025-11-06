# Frontend Build Instructions

## Prerequisites

- Node.js 18+ and npm

## Installation

```bash
cd /workspace/frontend
npm install
```

## Development

```bash
# Start dev server (runs on http://localhost:3000)
npm run dev
```

## Build for Production

```bash
# TypeScript compile + Vite build
npm run build

# Output: dist/ directory
```

## Testing

```bash
# Run unit tests
npm test

# Run E2E tests (requires backend running)
npm run test:e2e

# Run linter
npm run lint
```

## Verification Checklist

Before running the frontend:

1. ✅ Backend API running on http://localhost:8000
2. ✅ Authentication token obtained from backend logs
3. ✅ Visit http://localhost:3000/?token={your-token}
4. ✅ Dashboard should load and display

## Common Issues

### Dependencies Not Installed

```bash
cd /workspace/frontend
npm install
```

### Backend Not Running

Start the backend:
```bash
cd /workspace
python -m uvicorn codetoreum.adapters.primary.fastapi_app:app --reload
```

### Auth Token Expired

Restart backend to generate new token

### WebSocket Not Connecting

Check:
- Backend WebSocket endpoint is accessible
- Token is valid
- No proxy/firewall blocking WebSocket connections

# Codetoreum Configuration UI

Modern React-based web interface for managing Codetoreum Gen 2 configuration.

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **React Router** - Client-side routing
- **TanStack Query** - Data fetching and caching
- **React Hook Form** - Form management
- **Zod** - Schema validation
- **Axios** - HTTP client

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Backend API running on `http://localhost:8000`

### Installation

```bash
# Install dependencies
npm install
```

### Development

```bash
# Start development server (http://localhost:3000)
npm run dev
```

The dev server includes a proxy to the backend API, so API requests to `/api/*` will be forwarded to `http://localhost:8000`.

### Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

### Testing

```bash
# Run unit tests
npm test

# Run E2E tests
npm run test:e2e

# Run linter
npm run lint
```

## Project Structure

```
src/
├── api/                    # API client
│   └── client.ts          # Axios client with typed endpoints
├── components/
│   └── ui/                # Reusable UI components
│       ├── button.tsx
│       ├── input.tsx
│       └── card.tsx
├── hooks/                 # Custom React hooks (future)
├── lib/
│   └── utils.ts          # Utility functions
├── pages/
│   ├── ProjectConfigPage.tsx    # ✅ Complete
│   ├── WorkflowConfigPage.tsx   # Stub
│   ├── AgentConfigPage.tsx      # Stub
│   └── ConfigHistoryPage.tsx    # Stub
├── types/
│   └── index.ts          # TypeScript type definitions
├── App.tsx               # Main app with routing
├── main.tsx             # Entry point
└── index.css            # Global styles + Tailwind
```

## Features

### Implemented ✅

- **Project Configuration Management**
  - Environment variables (add, edit, delete)
  - Secret encryption support
  - Mounted commands management
  - Sub-agents configuration
  - Repository settings display

### Planned 🚧

- **Workflow Configuration**
  - Pipeline editor
  - Stage management
  - Transition configuration

- **Agent Configuration**
  - Agent list and editor
  - Model and timeout settings
  - MCP server configuration
  - Capabilities and constraints

- **Configuration History**
  - Change log
  - Diff viewer
  - Rollback functionality

## API Integration

The frontend communicates with the Codetoreum backend REST API at `/api/v1`.

### Environment Configuration

By default, the Vite dev server proxies API requests to `http://localhost:8000`. To change this, edit `vite.config.ts`:

```typescript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://your-backend-url:port',
        changeOrigin: true,
      },
    },
  },
})
```

For production builds, set the API URL via environment variable:

```bash
VITE_API_URL=https://api.codetoreum.com npm run build
```

## Development Guidelines

### Adding New Pages

1. Create page component in `src/pages/`
2. Add route in `src/App.tsx`
3. Add navigation link in nav bar
4. Create API methods in `src/api/client.ts`
5. Add TypeScript types in `src/types/index.ts`

Example:
```tsx
// src/pages/MyNewPage.tsx
export default function MyNewPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold">My New Page</h2>
      {/* Page content */}
    </div>
  )
}

// src/App.tsx
import MyNewPage from './pages/MyNewPage'

<Routes>
  <Route path="/my-page" element={<MyNewPage />} />
  {/* other routes */}
</Routes>
```

### Using the API Client

```tsx
import { useQuery, useMutation } from '@tanstack/react-query'
import { projectConfigApi } from '../api/client'

// Fetch data
const { data, isLoading, error } = useQuery({
  queryKey: ['projectConfig', projectName],
  queryFn: () => projectConfigApi.get(projectName),
})

// Update data
const mutation = useMutation({
  mutationFn: (updates) => projectConfigApi.update(projectName, updates),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['projectConfig'] })
  },
})
```

### Styling

Use Tailwind CSS utility classes:

```tsx
<div className="flex items-center space-x-4 p-4 border rounded-md">
  <span className="text-lg font-bold">Title</span>
  <Button variant="primary">Click me</Button>
</div>
```

Combine classes with the `cn()` utility:

```tsx
import { cn } from '@/lib/utils'

<div className={cn(
  'base-styles',
  isActive && 'active-styles',
  'more-styles'
)}>
  Content
</div>
```

### Form Handling

Use React Hook Form with Zod validation:

```tsx
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

const schema = z.object({
  name: z.string().min(1, 'Name is required'),
  value: z.string().min(1, 'Value is required'),
})

function MyForm() {
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
  })

  const onSubmit = (data) => {
    console.log(data)
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <Input {...register('name')} />
      {errors.name && <span className="text-red-500">{errors.name.message}</span>}
      <Button type="submit">Submit</Button>
    </form>
  )
}
```

## Environment Variables

Create `.env.local` for local development:

```bash
VITE_API_URL=http://localhost:8000
```

Access in code:

```typescript
const apiUrl = import.meta.env.VITE_API_URL
```

## Deployment

### Build for Production

```bash
npm run build
```

This creates a `dist/` folder with optimized static files.

### Deployment Options

1. **Serve from FastAPI**: Mount the `dist` folder as static files in your FastAPI app
2. **Static File Hosting**: Deploy to Vercel, Netlify, or S3+CloudFront
3. **Nginx**: Use Nginx to serve static files and proxy API requests

Example Nginx configuration:

```nginx
server {
    listen 80;
    server_name config.codetoreum.com;

    root /var/www/codetoreum-ui/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
    }
}
```

## Troubleshooting

### API Requests Failing

- Ensure backend is running on `http://localhost:8000`
- Check proxy configuration in `vite.config.ts`
- Check browser console for CORS errors

### Build Errors

- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Clear Vite cache: `rm -rf node_modules/.vite`

### TypeScript Errors

- Regenerate types: Update `src/types/index.ts` to match backend models
- Check TypeScript version: Should be 5.3.3+

## Contributing

1. Create a feature branch
2. Make changes
3. Run linter: `npm run lint`
4. Run tests: `npm test`
5. Create pull request

## License

See main project LICENSE file.

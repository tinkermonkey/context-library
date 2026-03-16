# Context Library UI

Frontend for the Context Library semantic search and data browser application.

## Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Environment Variables

### `VITE_API_BASE_URL` (Production)

The API base URL for production builds. If not set:
- **Development**: `/api` (proxied by Vite dev server to `http://localhost:8000`)
- **Production**: `''` (routes at root, for co-located frontend/API deployments)

Use `VITE_API_BASE_URL` when the frontend and API are not co-located:
```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

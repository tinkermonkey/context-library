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

The API base URL for production builds. Defaults to `/api` if not set.

Use this when the frontend and API are not co-located:
```bash
VITE_API_BASE_URL=https://api.example.com npm run build
```

During development, the Vite dev server proxies `/api` to `http://localhost:8000`.

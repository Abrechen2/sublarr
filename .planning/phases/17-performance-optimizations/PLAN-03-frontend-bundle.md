# Plan 17-03: Frontend Bundle Optimization — Code Splitting + staleTime Fix

## Goal
Reduce initial bundle size with Vite code splitting + lazy route loading,
and fix the staleTime=0 issue for subtitle content.

## Changes

### 1. frontend/vite.config.ts — Add code splitting

Current config has no rollupOptions — all pages bundled together.

Add manual chunks to separate heavy dependencies:

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React runtime
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // TanStack Query
          'vendor-query': ['@tanstack/react-query'],
          // CodeMirror (subtitle editor — heaviest dep)
          'vendor-codemirror': [
            '@codemirror/state',
            '@codemirror/view',
            '@codemirror/lang-javascript',
          ],
          // Socket.IO
          'vendor-socketio': ['socket.io-client'],
        },
      },
    },
  },
  resolve: { ... },  // keep existing
  optimizeDeps: { ... },  // keep existing
  server: { ... },  // keep existing
})
```

Check which codemirror packages are actually installed:
`ls frontend/node_modules/@codemirror/` — only include installed ones.

### 2. frontend/src/App.tsx — Lazy-load heavy routes

Convert static page imports to React.lazy() for routes not needed on initial load.
Keep Dashboard, Activity (most used) as eager. Lazy-load everything else.

Pattern:
```typescript
// Before (static import):
import Settings from '@/pages/Settings'
import SubtitleEditor from '@/pages/SubtitleEditor'

// After (lazy):
const Settings = lazy(() => import('@/pages/Settings'))
const SubtitleEditor = lazy(() => import('@/pages/SubtitleEditor'))
```

Wrap router in `<Suspense fallback={<div>Loading...</div>}>` if not already done.

Check App.tsx to see current import pattern and which pages exist.
Lazy-load candidates (not shown on app start): Settings, Logs, History,
Blacklist, SubtitleEditor, Statistics, Cleanup.

### 3. frontend/src/hooks/useApi.ts — Fix staleTime=0 for subtitle content

Line ~977:
```typescript
// Old:
staleTime: 0,  // Always refetch (file may change externally)

// New: 30s cache — user can manually refresh if needed
staleTime: 30_000,
```

The subtitle editor already has a "reload" button for manual refresh.
Always fetching from disk on every focus is wasteful.

## Verification
- `cd frontend && npm run build` — check chunk sizes in output
  - Target: no single chunk >500KB
  - vendor-codemirror should be its own chunk, not in main bundle
- `npm test` passes
- Open editor page: verify subtitle content loads (not broken by staleTime change)
- Check App.tsx Suspense wrapping is correct (no blank screens)

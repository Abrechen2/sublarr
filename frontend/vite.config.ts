import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

const projectRoot = __dirname
const reactPath = path.resolve(projectRoot, 'node_modules/react')
const reactDomPath = path.resolve(projectRoot, 'node_modules/react-dom')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  experimental: {
    // Vite 8.0.x bug: FullBundleDevEnvironment (Rolldown) does not replace
    // __BUNDLED_DEV__ in @vite/client, causing ReferenceError → blank page.
    // Disable until fixed upstream.
    bundledDev: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('react-dom') || id.includes('react-router-dom') || (id.includes('node_modules/react/') && !id.includes('react-dom'))) {
            return 'vendor-react'
          }
          if (id.includes('@tanstack/react-query')) return 'vendor-query'
          if (id.includes('@codemirror/state') || id.includes('@codemirror/view')) return 'vendor-codemirror'
          if (id.includes('socket.io-client')) return 'vendor-socketio'
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(projectRoot, './src'),
      react: reactPath,
      'react-dom': reactDomPath,
      'react-dom/client': path.resolve(reactDomPath, 'client.js'),
    },
    dedupe: ['react', 'react-dom'],
  },
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react-router-dom',
      'react-router',
      'react-hotkeys-hook',
    ],
    esbuildOptions: {
      alias: {
        react: reactPath,
        'react-dom': reactDomPath,
      },
    },
  },
  server: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
    },
    proxy: {
      '/api': 'http://localhost:5765',
      '/socket.io': {
        target: 'http://localhost:5765',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})

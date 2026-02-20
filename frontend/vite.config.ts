import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

const projectRoot = __dirname
const reactPath = path.resolve(projectRoot, 'node_modules/react')
const reactDomPath = path.resolve(projectRoot, 'node_modules/react-dom')

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-query': ['@tanstack/react-query'],
          'vendor-codemirror': ['@codemirror/state', '@codemirror/view'],
          'vendor-socketio': ['socket.io-client'],
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
    proxy: {
      '/api': 'http://localhost:5765',
      '/socket.io': {
        target: 'http://localhost:5765',
        ws: true,
      },
    },
  },
})

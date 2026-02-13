import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen flex items-center justify-center p-8"
          style={{ backgroundColor: 'var(--bg-primary)' }}
        >
          <div
            className="max-w-md w-full rounded-xl p-8 text-center"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
            }}
          >
            <div
              className="w-12 h-12 rounded-lg mx-auto mb-4 flex items-center justify-center"
              style={{ backgroundColor: 'var(--warning-bg)' }}
            >
              <AlertTriangle size={24} style={{ color: 'var(--warning)' }} />
            </div>
            <h1 className="text-lg font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
              Something went wrong
            </h1>
            <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
              An unexpected error occurred. Please reload the page.
            </p>
            {this.state.error && (
              <pre
                className="text-xs text-left p-3 rounded-lg mb-4 overflow-auto max-h-32"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  color: 'var(--error)',
                  fontFamily: 'var(--font-mono)',
                  border: '1px solid var(--border)',
                }}
              >
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReload}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white hover:opacity-90"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <RefreshCw size={14} />
              Reload Page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

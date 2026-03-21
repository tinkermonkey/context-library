import type { ReactNode } from 'react';
import { Component } from 'react';

/**
 * Props for the ErrorBoundary component.
 */
interface ErrorBoundaryProps {
  children: ReactNode;
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
  fallback?: (error: Error, resetError: () => void) => ReactNode;
}

/**
 * State for the ErrorBoundary component.
 */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * React ErrorBoundary to catch runtime rendering errors in domain view components.
 *
 * ErrorBoundary is a class component that catches errors thrown during rendering,
 * in lifecycle methods, and in constructors of child components. Unlike Suspense,
 * which only catches promises being thrown, ErrorBoundary catches actual exceptions.
 *
 * This is critical for domain views where bad metadata shapes or rendering errors
 * would otherwise crash the entire page.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error for debugging
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    // Call optional onError callback
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  resetError = () => {
    this.setState({
      hasError: false,
      error: null,
    });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.resetError);
      }

      // Default error UI
      return (
        <div className="p-8">
          <div className="bg-red-50 p-6 rounded border border-red-200">
            <h2 className="text-red-900 font-bold text-lg mb-2">Error Loading View</h2>
            <p className="text-red-800 mb-4">
              An unexpected error occurred while rendering this domain view:
            </p>
            <div className="bg-red-100 p-3 rounded font-mono text-sm text-red-900 mb-4 overflow-auto max-h-40">
              {this.state.error.message}
            </div>
            <button
              onClick={this.resetError}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-semibold"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
